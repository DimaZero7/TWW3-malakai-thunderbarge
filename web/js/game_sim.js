// The game's side, simulated: what the game gives for free and the mod only calls (docs/design/panel-upgrades-proposal.md, section 2, variant A).
// Treasury, development points, the horde's buildings, the construction queue, the turn. Nothing of this moves to the game: there it is the game
// itself, read and commanded by src/tww3_mtb_game.lua (the adapter). Each method names what stands for it in the game. Rules of the game that this
// file guesses are marked "guess". The order of a turn's events is the game's as the adapter hands it on (docs/design/port-to-game.md 8.2):
// FactionTurnEnd; the game dismantles and completes (its completions come before the faction's turn start, the adapter holds them back);
// BuildingDemolished (the adapter's saved mark checked); FactionTurnStart; then each completion.
// tools/tests/fake_game.lua is this file in Lua, method for method.

const GROWTH = 'wh_main_effect_hordebuilding_growth_core';     // «Рост орды: +N» of a horde's building

export class GameSim {
    constructor(data, sim) {
        this.data = data;
        this.prefix = data.prefix;
        this.turn = sim.turn;
        this.gold = sim.gold;
        this.income = sim.income;          // the faction's income per turn: not modelled, a number from web/data/sim.json
        // the horde's development points (GAME: HordeContext.DevelopmentPoints; 0 at the start of a campaign, run 20261114-230723). null: not
        // modelled (the model then never locks by points)
        this.dev = sim.dev_points ?? null;
        // The horde's growth makes them (GAME: HordeContext.AccumulatedGrowth / GrowthPerTurn / GrowthThresholdForPoint; the game's data:
        // campaign_variables military_force_development_point_growth_threshold 20, military_force_development_max_development_points 50). A turn
        // adds its growth: the horde's own (growth_base: characters, technologies, events; guess 0 for Malakai, read by the session) and «Рост
        // орды: +N» of every level standing (wh_main_effect_hordebuilding_growth_core); each full threshold is one point. guess: the turn's growth
        // is counted with the buildings that stood during the turn, and the growth past the maximum of points is lost
        this.growthAcc = sim.growth || 0;
        this.growthBase = sim.growth_base || 0;
        this.growthNeed = sim.growth_threshold || 20;
        this.devMax = sim.dev_max ?? 50;
        this.growthOf = {};
        for (const r of data.tree_rows || []) this.growthOf[r.key] = (r.effects || []).filter(e => e && e.effect === GROWTH).reduce((s, e) => s + (e.value || 0), 0);
        // the game applies a command a moment later (run 20261115-012811: the slot read right after it was the old one); async: so here too, the
        // commands wait for tick() (the vectors' 'tick'; the adapter's re-read on the game's next ticks), then CommandResult {key, kind}
        this.async = !!sim.async;
        this.commands = [];
        this.demolishMode = sim.demolish || 'chain';     // 'chain': as the game, the whole building goes; 'step_down': the level below comes back
        // the game asks before it cancels a construction of an earlier turn (probe 14.11, item 12). The page has no game window: off there (the
        // cancel is taken at once); the vectors turn it on and answer it (answer_cancel)
        this.askCancel = !!sim.ask_cancel;
        // GAME: the adapter's crew_pays (Malakai on the barge, the places written): the page has no such state and no method; a vector that
        // gives sim.crew_pays has one (the turn's upkeep is then taken only while it says true)
        if (sim.crew_pays !== undefined) {
            this.crewPays = !!sim.crew_pays;
            this.crew_pays = () => this.crewPays;
        }
        this.built = new Set(sim.built.map(s => this.prefix + s));
        this.queue = new Map();             // level key -> {turns_left, paid, dev, turn}
        this.dismantles = new Set();        // the keys whose Dismantle was given this turn: they stand until the turn ends
        this.asked = null;                  // the key whose cancel waits for the game's window
        // the share of a level's price the game gives back when its dismantled building goes (the game's data: campaign_variables
        // building_dismantle_recoup_multiplier_when_full_health 0.6; run 20261115-065150: +600 for a level of 1000), in per cent
        this.refundPct = sim.dismantle_refund ?? 60;
        // a moment of the game the panel gives way to (GAME: the adapter's blocker()): null, or 'turn' | 'battle' | 'dilemma' | 'event' | 'panel' |
        // 'dialog'. The page has none of them; the vectors set it (modal)
        this.modal = null;
        this.listeners = {};
        this.levels = {};
        for (const row of data.hull) this.levels[row.key] = row;
        for (const chain of data.chains) for (const row of chain.levels) this.levels[row.key] = row;
    }

    on(event, fn) { (this.listeners[event] ||= []).push(fn); }      // core:add_listener
    emit(event, ctx) { for (const fn of this.listeners[event] || []) fn(ctx); }

    // cm:get_faction(...):treasury()
    treasury() { return this.gold; }
    // GAME: DatabaseRecordContext("CcoBuildingLevelRecord", key).CreateCost(this) / .DevelopmentPointCost(this) from Malakai's context
    cost(key) { return this.levels[key].cost; }
    dev_cost(key) { return this.levels[key].dev || 0; }
    // GAME: MilitaryForceContext.HordeContext.DevelopmentPoints
    development_points() { return this.dev; }
    set_growth(n) { this.growthAcc = n; }        // the session's replay: the game's accumulated growth
    // GAME: HordeContext.GrowthPerTurn: the horde's own and the standing levels' «Рост орды»
    growthPerTurn() { return this.growthBase + [...this.built].reduce((s, k) => s + (this.growthOf[k] || 0), 0); }
    // GAME: {now: AccumulatedGrowth, per_turn: GrowthPerTurn, need: GrowthThresholdForPoint, turns: TurnsUntilNextGrowthPoint (null: never),
    // max: HasMaxDevelopmentPoints}; null when the points are not modelled
    growth() {
        if (this.dev === null) return null;
        const per = this.growthPerTurn(), max = this.dev >= this.devMax;
        return {now: this.growthAcc, per_turn: per, need: this.growthNeed, turns: per > 0 && !max ? Math.ceil((this.growthNeed - this.growthAcc) / per) : null, max};
    }
    // GAME: HordeContext.BuildingSlotList: what stands now. A higher level of a chain replaces the lower one in its slot; the mod counts the lower one as standing
    // (src/tww3_mtb_crew.lua, CONFIG.levels), so does this.
    has_building(key) {
        const row = this.levels[key];
        if (this.built.has(key)) return true;
        return [...this.built].some(k => this.levels[k] && row && this.levels[k].chain === row.chain && this.levels[k].level > row.level);
    }
    // GAME: BuildingSlotList.At(n) under construction, TurnsToCompletion (readable outside the tree, check run 04.11)
    under_construction(key) { return this.queue.has(key) ? this.queue.get(key).turns_left : null; }
    isHull(key) { return this.data.hull_tiers ? key in this.data.hull_tiers : this.data.hull.some(h => h.key === key); }

    // GAME: the order. In the game: common.call_context_command on
    //   DatabaseRecordContext("CcoBuildingLevelRecord", key):IssueCommandForBuildingBrowser(MilitaryForceContext.HordeContext.BuildingSlotList.At(n))
    // from the character's context, which works without selecting Malakai (check run 04.11). The game takes create_cost and the points itself;
    // it refuses silently (the command answers ok) when the gold or the points are short (run 20261114-230723).
    issue_building_command(key) {
        const row = this.levels[key];
        if (!row) return false;
        if (this.async) { this.commands.push({key, kind: this.queue.has(key) ? 'cancel' : 'order'}); return 'pending'; }
        return this.applyCommand(key);
    }
    applyCommand(key) {
        const row = this.levels[key];
        if (this.queue.has(key)) {               // the same command again cancels (check run 04.11)
            this.applyCancel(key);
            return true;
        }
        const dev = this.dev_cost(key);
        if (this.gold < row.cost || (this.dev !== null && this.dev < dev)) return true;     // refused: nothing happens
        this.gold -= row.cost;
        if (this.dev !== null) this.dev -= dev;
        this.queue.set(key, {turns_left: row.turns, paid: row.cost, dev, turn: this.turn});
        return true;
    }
    // GAME: the adapter's reason of a refused order, read from the game's gates (none here: the model does not order what the game refuses)
    refusal() { return null; }

    // GAME: the same command once more. A construction of this turn: the whole price back (check run 04.11). Of an earlier turn: the game's window
    // asks first and nothing changes until it is answered (probe 14.11, item 12). guess: the whole price and the points back in both cases.
    cancel_construction(key) {
        if (!this.queue.get(key)) return false;
        if (this.async) { this.commands.push({key, kind: 'cancel'}); return 'pending'; }
        return this.applyCancel(key);
    }
    applyCancel(key) {
        const q = this.queue.get(key);
        if (!q) return false;
        if (this.askCancel && q.turn < this.turn) { this.asked = key; return true; }
        this.refund(key);
        return true;
    }
    // the game's next tick: the waiting commands applied, each told (GAME: the adapter's re-read of the slot, CommandResult)
    tick() {
        const list = this.commands;
        this.commands = [];
        for (const c of list) {
            if (c.kind === 'order') this.applyCommand(c.key); else this.applyCancel(c.key);
            this.emit('CommandResult', {key: c.key, kind: c.kind});
        }
        return list.length;
    }
    // GAME: what a Dismantle takes: the slot's whole building, its lower levels with it (run 20261115-012811); the page's step_down: the level
    // alone. The top first
    dismantle_takes(key) {
        const row = this.levels[key];
        if (!row || this.demolishMode === 'step_down') return [key];
        const out = [];
        for (let lv = row.level; lv >= 0; lv--) { const l = Object.values(this.levels).find(x => x.chain === row.chain && x.level === lv); if (l) out.push(l.key); }
        return out;
    }
    refund(key) {
        const q = this.queue.get(key);
        this.gold += q.paid;
        if (this.dev !== null) this.dev += q.dev || 0;
        this.queue.delete(key);
    }
    // GAME: the confirmation window, waiting for the player; its answer (the vectors' answer_cancel; the player's tick or cross in the game)
    cancel_asked(key) { return this.asked === key; }
    answer_cancel(yes) {
        const key = this.asked;
        if (!key) return false;
        this.asked = null;
        if (yes && this.queue.has(key)) this.refund(key);
        this.emit('CancelAnswered', {key, cancelled: !!yes});
        return true;
    }

    // GAME: the building in a slot: BuildingSlotList.At(n) holds one level of a chain, the higher one once upgraded
    standing(key) { return this.built.has(key); }

    // GAME: the game's own moment that takes the screen (another faction's turn, a battle, a dilemma, an event, its panel or window), or null
    blocker() { return this.modal; }

    // GAME: what the game gives back when the dismantled level goes: BuildingSlotList.At(n).BuildingContext.DismantleRefundAmount (the adapter;
    // the data's rule when it does not answer): the share of the level's own price, rounded down. guess: of the level's price, not the line's
    dismantle_refund(key) {
        const row = this.levels[key];
        if (!row) return 0;
        const v = row.cost * this.refundPct;
        return (v - v % 100) / 100;
    }

    // GAME: BuildingSlotList.At(n).Dismantle after its CanDismantle (false for the hull; guess: false while its slot has a construction). The
    // building stands until the turn ends (probe 14.11, 8.2; runs of 03.11), then the game pays dismantle_refund (run 20261115-065150)
    dismantle(key) {
        if (!this.built.has(key) || this.isHull(key) || this.dismantling(key)) return false;
        const row = this.levels[key];
        if ([...this.queue.keys()].some(k => this.levels[k] && this.levels[k].chain === row.chain)) return false;
        this.dismantles.add(key);
        return true;
    }
    // GAME: the adapter's saved mark: a Dismantle given this turn to a level of this key's chain, the chain still standing
    dismantling(key) {
        const row = this.levels[key];
        if (!row) return false;
        return [...this.dismantles].some(k => this.levels[k].chain === row.chain && this.built.has(k));
    }
    // the end of the turn: the dismantled building goes (the game's)
    takeDown(key) {
        this.built.delete(key);
        const row = this.levels[key];
        if (this.demolishMode === 'step_down') {       // the page's rule, not the game's: one level down
            const below = Object.values(this.levels).find(l => l.chain === row.chain && l.level === row.level - 1);
            if (below) this.built.add(below.key);
            return;
        }
        // the chain falls back to nothing: the game removes the whole chain of the slot (docs/summary.md: «Снос уровня цепочки снимает всю цепочку»)
        for (const k of [...this.built]) if (this.levels[k] && this.levels[k].chain === row.chain) this.built.delete(k);
    }

    // Debug only (not the game): the building stands at once, no turn, no gold, no points; the same event as a completion.
    debug_complete(key) {
        this.tick();
        const row = this.levels[key];
        if (!row || this.has_building(key)) return false;
        this.queue.delete(key);
        if (this.asked === key) this.asked = null;
        for (const k of [...this.dismantles]) if (this.levels[k].chain === row.chain) this.dismantles.delete(k);
        for (const k of [...this.built]) if (this.levels[k] && this.levels[k].chain === row.chain && this.levels[k].level < row.level) this.built.delete(k);
        this.built.add(key);
        this.emit('MilitaryForceBuildingCompleteEvent', {building: key});
        return true;
    }

    // A script's cm:add_building_to_force (tests, the session): the level stands at once in its line's slot, no event, nothing paid
    script_stand(key) {
        this.tick();
        const row = this.levels[key];
        if (!row) return false;
        for (const k of [...this.built]) if (this.levels[k] && this.levels[k].chain === row.chain) this.built.delete(k);
        this.built.add(key);
        return true;
    }

    // A building gone without an event the mod hears (the stock horde tab's dismantle, a script): its line's slot empty at once
    script_remove(key) {
        this.tick();
        const row = this.levels[key];
        if (!row) return false;
        for (const k of [...this.built]) if (this.levels[k] && this.levels[k].chain === row.chain) this.built.delete(k);
        return true;
    }

    // The page's own saving (not the game's save): plain data and back. The dismantle marks are the adapter's saved value in the game.
    snapshot() {
        return {turn: this.turn, gold: this.gold, dev: this.dev, growth: this.growthAcc, built: [...this.built], queue: [...this.queue].map(([k, q]) => [k, {...q}]),
                dismantles: [...this.dismantles]};
    }
    restore(s) {
        this.turn = s.turn; this.gold = s.gold;
        if (s.dev !== undefined) this.dev = s.dev;
        if (s.growth !== undefined) this.growthAcc = s.growth;
        this.built = new Set(s.built.filter(k => this.levels[k]));
        this.queue = new Map(s.queue.filter(([k]) => this.levels[k]).map(([k, q]) => [k, {...q}]));
        this.dismantles = new Set((s.dismantles || []).filter(k => this.levels[k]));
        this.asked = null;
    }

    // GAME: the player's own end turn button, then the turn of the world, then Malakai's next turn, in the order the adapter hands the events on.
    end_turn() {
        this.tick();        // a command is applied long before a turn can end
        this.emit('FactionTurnEnd', {turn: this.turn});
        // the turn's growth, with the buildings that stood during it
        if (this.dev !== null) {
            this.growthAcc = Math.max(0, this.growthAcc + this.growthPerTurn());
            while (this.growthNeed > 0 && this.growthAcc >= this.growthNeed) {
                this.growthAcc -= this.growthNeed;
                if (this.dev < this.devMax) this.dev += 1;
            }
        }
        this.asked = null;                  // guess: the game's window does not outlive the turn
        const gone = [...this.dismantles].filter(k => this.built.has(k));
        const refunds = {};
        for (const k of gone) { refunds[k] = this.dismantle_refund(k); this.gold += refunds[k]; }
        for (const k of gone) this.takeDown(k);
        this.dismantles.clear();
        const done = [];
        for (const [key, q] of this.queue) {
            q.turns_left -= 1;
            if (q.turns_left <= 0) done.push(key);
        }
        // the game completes them now (its events come with the old turn number, before the turn start: the adapter holds them back)
        for (const key of done) {
            this.queue.delete(key);
            const row = this.levels[key];
            for (const k of [...this.built]) if (this.levels[k] && this.levels[k].chain === row.chain && this.levels[k].level < row.level) this.built.delete(k);
            this.built.add(key);
        }
        this.turn += 1;
        this.gold += this.income;
        for (const key of gone) this.emit('BuildingDemolished', {key, refund: refunds[key]});
        this.emit('FactionTurnStart', {turn: this.turn});
        for (const key of done) this.emit('MilitaryForceBuildingCompleteEvent', {building: key});
    }
}
