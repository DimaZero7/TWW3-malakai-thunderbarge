// The game's side, simulated: what the game gives for free and the mod only calls (docs/design/panel-upgrades-proposal.md, section 2, variant A).
// Treasury, the horde's buildings, the construction queue, the turn. Nothing of this moves to the game: there it is the game itself.
// Each method names what stands for it in the game. Rules of the game that this file guesses are marked "guess".

export class GameSim {
    constructor(data, sim) {
        this.data = data;
        this.prefix = data.prefix;
        this.turn = sim.turn;
        this.gold = sim.gold;
        this.income = sim.income;
        this.demolishMode = sim.demolish || 'chain';     // 'chain': as the game, the whole building goes; 'step_down': the level below comes back          // the faction's income per turn: not modelled, a number from web/data/sim.json
        this.built = new Set(sim.built.map(s => this.prefix + s));
        this.queue = new Map();             // level key -> {turns_left, paid}
        this.listeners = {};
        this.levels = {};
        for (const row of data.hull) this.levels[row.key] = row;
        for (const chain of data.chains) for (const row of chain.levels) this.levels[row.key] = row;
    }

    on(event, fn) { (this.listeners[event] ||= []).push(fn); }      // core:add_listener
    emit(event, ctx) { for (const fn of this.listeners[event] || []) fn(ctx); }

    // cm:get_faction(...):treasury()
    treasury() { return this.gold; }
    // GAME: HordeContext.BuildingSlotList: what stands now. A higher level of a chain replaces the lower one in its slot; the mod counts the lower one as standing
    // (src/tww3_mtb_crew.lua, CONFIG.levels), so does this.
    has_building(key) {
        const row = this.levels[key];
        if (this.built.has(key)) return true;
        return [...this.built].some(k => this.levels[k] && row && this.levels[k].chain === row.chain && this.levels[k].level > row.level);
    }
    // GAME: BuildingSlotList.At(n) under construction, TurnsToCompletion (readable outside the tree, check run 04.11)
    under_construction(key) { return this.queue.has(key) ? this.queue.get(key).turns_left : null; }

    // GAME: the order. In the game: common.call_context_command on
    //   DatabaseRecordContext("CcoBuildingLevelRecord", key):IssueCommandForBuildingBrowser(SelectedCharacter.MilitaryForceContext.HordeContext.BuildingSlotList.At(n))
    // from the character's context, which works without selecting Malakai (check run 04.11). The game takes create_cost from the treasury itself.
    issue_building_command(key) {
        const row = this.levels[key];
        if (!row) return false;
        if (this.queue.has(key)) {               // the same command again cancels (check run 04.11)
            this.cancel_construction(key);
            return true;
        }
        if (this.gold < row.cost) return false;  // the game refuses: the panel should not have offered it
        this.gold -= row.cost;
        this.queue.set(key, {turns_left: row.turns, paid: row.cost});
        return true;
    }

    // GAME: the same command once more, or the slot's Cancel. guess: the whole price comes back, as the game does for a construction cancelled in its first turn
    cancel_construction(key) {
        const q = this.queue.get(key);
        if (!q) return false;
        this.gold += q.paid;
        this.queue.delete(key);
        return true;
    }

    // GAME: the building in a slot: BuildingSlotList.At(n) holds one level of a chain, the higher one once upgraded
    standing(key) { return this.built.has(key); }

    // GAME: BuildingSlotList.At(n).Dismantle; the hull has CanDismantle = false. guess: no gold back (DismantleRefundAmount not read)
    dismantle(key) {
        if (!this.built.has(key)) return false;
        this.built.delete(key);
        const row = this.levels[key];
        if (this.demolishMode === 'step_down') {       // the page's rule, not the game's: one level down
            const below = Object.values(this.levels).find(l => l.chain === row.chain && l.level === row.level - 1);
            if (below) this.built.add(below.key);
            this.emit('BuildingDemolished', {key});
            return true;
        }
        // the chain falls back to nothing: the game removes the whole chain of the slot (docs/summary.md: «Снос уровня цепочки снимает всю цепочку»)
        for (const k of [...this.built]) if (this.levels[k] && this.levels[k].chain === row.chain) this.built.delete(k);
        this.emit('BuildingDemolished', {key});
        return true;
    }

    // GAME: the player's own end turn button. At the start of the next turn the game finishes what is due and fires MilitaryForceBuildingCompleteEvent,
    // which the mod already follows (src/tww3_mtb_crew.lua, on_building).
    end_turn() {
        this.turn += 1;
        this.gold += this.income;
        const done = [];
        for (const [key, q] of this.queue) {
            q.turns_left -= 1;
            if (q.turns_left <= 0) done.push(key);
        }
        this.emit('FactionTurnStart', {turn: this.turn});
        for (const key of done) {
            this.queue.delete(key);
            const row = this.levels[key];
            for (const k of [...this.built]) if (this.levels[k] && this.levels[k].chain === row.chain && this.levels[k].level < row.level) this.built.delete(k);
            this.built.add(key);
            this.emit('MilitaryForceBuildingCompleteEvent', {building: key});
        }
    }
}
