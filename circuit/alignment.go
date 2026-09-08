package circuit

import (
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
	"github.com/consensys/gnark/std/math/cmp"
)

const (
	MaxTrace      = 8
	MaxMoves      = 10
	FinalState    = 5
	DomainTraceV1 = 20260908
)

const (
	MovePad = iota
	MoveSync
	MoveLog
	MoveModel
)

// AlignmentCircuit verifies one private trace against the public, fixed
// healthcare model Admit(1) -> Examine(2) -> Approve(3) -> Treat(4) ->
// Discharge(5). EmergencyTest is activity 6 and has no model transition.
//
// The model and unit cost policy are circuit constants in this first public-
// model prototype. Trace, salt, and alignment remain private witnesses.
type AlignmentCircuit struct {
	// Public statement.
	TraceCommitment frontend.Variable `gnark:",public"`
	Threshold       frontend.Variable `gnark:",public"`
	ClaimedCost     frontend.Variable `gnark:",public"`

	// Private witness.
	TraceLength frontend.Variable
	Trace       [MaxTrace]frontend.Variable
	Salt        frontend.Variable
	MoveType    [MaxMoves]frontend.Variable
	LogActivity [MaxMoves]frontend.Variable
	Transition  [MaxMoves]frontend.Variable
}

func (c *AlignmentCircuit) Define(api frontend.API) error {
	// Goal 1: bind the exact private length and padded activity array to a salt.
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return err
	}
	h.Write(DomainTraceV1, c.TraceLength)
	for i := 0; i < MaxTrace; i++ {
		h.Write(c.Trace[i])
		isActiveTraceSlot := cmp.IsLess(api, i, c.TraceLength)
		// Canonical encoding: used slots contain a known non-zero activity;
		// unused slots are exactly zero.
		knownActivity := frontend.Variable(0)
		for activityID := 1; activityID <= 6; activityID++ {
			knownActivity = api.Add(
				knownActivity,
				api.IsZero(api.Sub(c.Trace[i], activityID)),
			)
		}
		api.AssertIsEqual(knownActivity, isActiveTraceSlot)
		api.AssertIsEqual(api.Mul(api.Sub(1, isActiveTraceSlot), c.Trace[i]), 0)
	}
	h.Write(c.Salt)
	api.AssertIsEqual(h.Sum(), c.TraceCommitment)
	api.AssertIsLessOrEqual(c.TraceLength, MaxTrace)

	pointer := frontend.Variable(0)
	state := frontend.Variable(0)
	cost := frontend.Variable(0)
	previousPad := frontend.Variable(0)

	for j := 0; j < MaxMoves; j++ {
		isPad := api.IsZero(c.MoveType[j])
		isSync := api.IsZero(api.Sub(c.MoveType[j], MoveSync))
		isLog := api.IsZero(api.Sub(c.MoveType[j], MoveLog))
		isModel := api.IsZero(api.Sub(c.MoveType[j], MoveModel))
		api.AssertIsEqual(api.Add(isPad, isSync, isLog, isModel), 1)

		// Padding is suffix-only: once PAD occurs, no later active move is legal.
		active := api.Sub(1, isPad)
		api.AssertIsEqual(api.Mul(previousPad, active), 0)
		previousPad = isPad

		consumeTrace := api.Add(isSync, isLog)
		consumeModel := api.Add(isSync, isModel)

		// Goal 2: select trace[pointer] and require the move to reproduce it.
		nextTraceActivity := frontend.Variable(0)
		for i := 0; i < MaxTrace; i++ {
			atIndex := api.IsZero(api.Sub(pointer, i))
			nextTraceActivity = api.Add(nextTraceActivity, api.Mul(atIndex, c.Trace[i]))
		}
		api.AssertIsEqual(
			api.Mul(consumeTrace, api.Sub(c.LogActivity[j], nextTraceActivity)),
			0,
		)
		api.AssertIsLessOrEqual(api.Add(pointer, consumeTrace), c.TraceLength)

		// Goal 3: legal public-model transition. For this linear model,
		// transition t has source t-1, label t, and target t.
		validTransition := frontend.Variable(0)
		for transitionID := 1; transitionID <= FinalState; transitionID++ {
			validTransition = api.Add(
				validTransition,
				api.IsZero(api.Sub(c.Transition[j], transitionID)),
			)
		}
		api.AssertIsEqual(validTransition, consumeModel)
		api.AssertIsEqual(
			api.Mul(consumeModel, api.Sub(state, api.Sub(c.Transition[j], 1))),
			0,
		)
		api.AssertIsEqual(
			api.Mul(isSync, api.Sub(c.LogActivity[j], c.Transition[j])),
			0,
		)

		// Unused witness fields cannot carry hidden alternative semantics.
		api.AssertIsEqual(api.Mul(api.Add(isLog, isPad), c.Transition[j]), 0)
		api.AssertIsEqual(api.Mul(api.Add(isModel, isPad), c.LogActivity[j]), 0)

		pointer = api.Add(pointer, consumeTrace)
		state = api.Add(state, consumeModel)
		cost = api.Add(cost, isLog, isModel) // visible deviations cost one
	}

	// Goal 4: consume the entire trace and reach the accepting model state.
	api.AssertIsEqual(pointer, c.TraceLength)
	api.AssertIsEqual(state, FinalState)

	// Goal 5: derive cost from moves; never trust the prover's cost.
	api.AssertIsEqual(cost, c.ClaimedCost)

	// Goal 6: enforce the public policy.
	api.AssertIsLessOrEqual(cost, c.Threshold)
	return nil
}
