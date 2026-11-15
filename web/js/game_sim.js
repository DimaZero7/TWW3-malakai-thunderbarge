// The game's side, simulated: what the game gives for free and the mod only calls (docs/design/panel-upgrades-proposal.md, section 2, variant A).
// Treasury, development points, the horde's buildings, the construction queue, the turn. Nothing of this moves to the game: there it is the game
// itself, read and commanded by src/tww3_mtb_game.lua (the adapter). Each method names what stands for it in the game. Rules of the game that this
// file guesses are marked "guess". The order of a turn's events is the game's as the adapter hands it on (docs/design/port-to-game.md 8.2):
// FactionTurnEnd; the game dismantles and completes (its completions come before the faction's turn start, the adapter holds them back);
// BuildingDemolished (the adapter's saved mark checked); FactionTurnStart; then each completion.
// tools/tests/fake_game.lua is this file in Lua, method for method.

export class GameSim {
    constructor(data, sim) {
        this.data = data;
        this.prefix = data.prefix;
        this.turn = sim.turn;
        this.gold = sim.gold;
        this.income = sim.income;          // the faction's income per turn: not modelled, a number from web/data/sim.json
        // the horde's development points (GAME: HordeContext.DevelopmentPoints; 0 at the start of a campaign, run 20261114-230723) and what a turn
        // adds (guess: the game's growth is not read yet). null: not modelled (the model then never locks by points)
        this.dev = sim.dev_points ?? null;
        this.devIncome = sim.dev_income || 0;
        this.demolishMode = sim.demolish || 'chain';     // 'chain': as the game, the whole building goes; 'step_down': the level below comes back
        // the game asks before it cancels a construction of an earlier turn (probe 14.11, item 12). The page has no game window: off there (the
        // cancel is taken at once); the vectors turn it on and answer it (answer_cancel)
        this.askCancel = !!sim.ask_cancel;
        this.built = new Set(sim.built.map(s => this.prefix + s));
        this.queue = new Map();             // level key -> {turns_left, paid, dev, turn}
        this.dismantles = new Set();        // the keys whose Dismantle was given this turn: they stand until the turn ends
        this.asked = null;                  // the key whose cancel waits for the game's window
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
        if (this.queue.has(key)) {               // the same command again cancels (check run 04.11)
            this.cancel_construction(key);
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
        const q = this.queue.get(key);
        if (!q) return false;
        if (this.askCancel && q.turn < this.turn) { this.asked = key; return true; }
        this.refund(key);
        return true;
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

    // GAME: BuildingSlotList.At(n).Dismantle after its CanDismantle (false for the hull; guess: false while its slot has a construction). The
    // building stands until the turn ends (probe 14.11, 8.2; runs of 03.11). guess: no gold back (DismantleRefundAmount not read)
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
        const row = this.levels[key];
        if (!row) return false;
        for (const k of [...this.built]) if (this.levels[k] && this.levels[k].chain === row.chain) this.built.delete(k);
        this.built.add(key);
        return true;
    }

    // The page's own saving (not the game's save): plain data and back. The dismantle marks are the adapter's saved value in the game.
    snapshot() {
        return {turn: this.turn, gold: this.gold, dev: this.dev, built: [...this.built], queue: [...this.queue].map(([k, q]) => [k, {...q}]),
                dismantles: [...this.dismantles]};
    }
    restore(s) {
        this.turn = s.turn; this.gold = s.gold;
        if (s.dev !== undefined) this.dev = s.dev;
        this.built = new Set(s.built.filter(k => this.levels[k]));
        this.queue = new Map(s.queue.filter(([k]) => this.levels[k]).map(([k, q]) => [k, {...q}]));
        this.dismantles = new Set((s.dismantles || []).filter(k => this.levels[k]));
        this.asked = null;
    }

    // GAME: the player's own end turn button, then the turn of the world, then Malakai's next turn, in the order the adapter hands the events on.
    end_turn() {
        this.emit('FactionTurnEnd', {turn: this.turn});
        this.asked = null;                  // guess: the game's window does not outlive the turn
        const gone = [...this.dismantles].filter(k => this.built.has(k));
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
        if (this.dev !== null) this.dev += this.devIncome;
        for (const key of gone) this.emit('BuildingDemolished', {key});
        this.emit('FactionTurnStart', {turn: this.turn});
        for (const key of done) this.emit('MilitaryForceBuildingCompleteEvent', {building: key});
    }
}
