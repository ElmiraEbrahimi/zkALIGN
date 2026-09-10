package circuit

import (
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
)

const (
	// These dimensions describe the real Petri net exported by the PM4Py
	// pipeline. Changing the discovered model requires regenerating
	// sepsis_model_gen.go and recompiling the circuit and Groth16 keys.
	PlaceCount        = 27
	TransitionCount   = 35
	ActivityCount     = 16
	MaxTraceEvents    = 185
	MaxAlignmentMoves = 64
	MerkleTreeDepth   = 32
	DomainTraceV2     = 20260910
	DomainMerkleLeaf  = 20260911
	DomainMerkleNode  = 20260912
)

const (
	// Zero is reserved for padding so unused fixed-array positions cannot be
	// confused with a real alignment move.
	MovePadding = iota
	MoveSynchronous
	MoveLogOnly
	MoveModelOnly
)

// SingleTracePetriNetCircuit proves that one private healthcare trace has a
// valid, complete alignment against the fixed public Sepsis Petri net.
type SingleTracePetriNetCircuit struct {
	// Public values are visible to the verifier. TraceCommitment hides the
	// salted trace; EventLogRoot binds it to the committed hospital log.
	TraceCommitment frontend.Variable `gnark:",public"`
	EventLogRoot    frontend.Variable `gnark:",public"`
	CostThreshold   frontend.Variable `gnark:",public"`
	AlignmentCost   frontend.Variable `gnark:",public"`

	// These fields are secret witness values. TraceEvents contains numeric
	// activity IDs 1..16 followed by zero padding up to MaxTraceEvents.
	TraceLength frontend.Variable
	TraceEvents [MaxTraceEvents]frontend.Variable
	TraceSalt   frontend.Variable
	TraceIndex  frontend.Variable
	MerklePath  [MerkleTreeDepth]frontend.Variable

	// Each alignment position is one parallel row across these arrays:
	// move type, consumed trace activity (or zero), and selected Petri-net
	// transition ID (or zero). Positions after AlignmentLength are all zero.
	AlignmentLength     frontend.Variable
	AlignmentMoveTypes  [MaxAlignmentMoves]frontend.Variable
	AlignmentActivities [MaxAlignmentMoves]frontend.Variable
	ModelTransitionIDs  [MaxAlignmentMoves]frontend.Variable
}

func (c *SingleTracePetriNetCircuit) Define(api frontend.API) error {
	// Goal 1: bind the exact private trace, length and padding to its commitment.
	traceHash, err := mimc.NewMiMC(api)
	if err != nil {
		return err
	}
	// Domain separation prevents the same field values from being interpreted
	// as a Merkle leaf or node hash elsewhere in the protocol.
	traceHash.Write(DomainTraceV2, c.TraceLength)
	usedTraceEvents := frontend.Variable(0)
	previousTracePadding := frontend.Variable(0)
	for eventIndex := 0; eventIndex < MaxTraceEvents; eventIndex++ {
		traceHash.Write(c.TraceEvents[eventIndex])
		// knownActivity becomes 1 exactly when the slot is one of activity IDs
		// 1..16. Together with isTracePadding, this rejects every other value.
		knownActivity := frontend.Variable(0)
		for activityID := 1; activityID <= ActivityCount; activityID++ {
			knownActivity = api.Add(knownActivity, api.IsZero(api.Sub(c.TraceEvents[eventIndex], activityID)))
		}
		isTracePadding := api.IsZero(c.TraceEvents[eventIndex])
		api.AssertIsEqual(api.Add(knownActivity, isTracePadding), 1)
		// Once zero padding begins, no later real event is allowed. This gives
		// every trace one canonical encoding for its commitment.
		api.AssertIsEqual(api.Mul(previousTracePadding, knownActivity), 0)
		previousTracePadding = isTracePadding
		usedTraceEvents = api.Add(usedTraceEvents, knownActivity)
	}
	api.AssertIsEqual(usedTraceEvents, c.TraceLength)
	traceHash.Write(c.TraceSalt)
	api.AssertIsEqual(traceHash.Sum(), c.TraceCommitment)

	// Also prove that this committed trace is one leaf of the public event-log
	// root. Path directions come from the private 32-bit trace index.
	leafHash, err := mimc.NewMiMC(api)
	if err != nil {
		return err
	}
	leafHash.Write(DomainMerkleLeaf, c.TraceIndex, c.TraceCommitment)
	currentHash := leafHash.Sum()
	// Bit level 0 chooses left/right at the leaf level, then each following
	// bit chooses the direction one level higher in the sparse Merkle tree.
	indexBits := api.ToBinary(c.TraceIndex, MerkleTreeDepth)
	for level := 0; level < MerkleTreeDepth; level++ {
		leftChild := api.Select(indexBits[level], c.MerklePath[level], currentHash)
		rightChild := api.Select(indexBits[level], currentHash, c.MerklePath[level])
		nodeHash, hashErr := mimc.NewMiMC(api)
		if hashErr != nil {
			return hashErr
		}
		nodeHash.Write(DomainMerkleNode+level, leftChild, rightChild)
		currentHash = nodeHash.Sum()
	}
	api.AssertIsEqual(currentHash, c.EventLogRoot)

	tracePosition := frontend.Variable(0)
	totalCost := frontend.Variable(0)
	// A marking is the complete Petri-net state. marking[p] is 1 when place p
	// currently holds a token. Several ones represent active parallel paths.
	marking := make([]frontend.Variable, PlaceCount)
	activeAlignmentMoves := frontend.Variable(0)
	previousMovePadding := frontend.Variable(0)
	for placeIndex := 0; placeIndex < PlaceCount; placeIndex++ {
		marking[placeIndex] = sepsisInitialMarking[placeIndex]
	}

	for moveIndex := 0; moveIndex < MaxAlignmentMoves; moveIndex++ {
		// Convert the numeric move type into four mutually exclusive Boolean
		// selectors. Their sum must be one, rejecting unknown move types.
		isPadding := api.IsZero(c.AlignmentMoveTypes[moveIndex])
		isSynchronous := api.IsZero(api.Sub(c.AlignmentMoveTypes[moveIndex], MoveSynchronous))
		isLogOnly := api.IsZero(api.Sub(c.AlignmentMoveTypes[moveIndex], MoveLogOnly))
		isModelOnly := api.IsZero(api.Sub(c.AlignmentMoveTypes[moveIndex], MoveModelOnly))
		api.AssertIsEqual(api.Add(isPadding, isSynchronous, isLogOnly, isModelOnly), 1)

		isActiveMove := api.Sub(1, isPadding)
		api.AssertIsEqual(api.Mul(previousMovePadding, isActiveMove), 0)
		previousMovePadding = isPadding
		activeAlignmentMoves = api.Add(activeAlignmentMoves, isActiveMove)
		// SYNC advances both sides, LOG advances only the trace, and MODEL
		// advances only the Petri net. PAD advances neither.
		consumesTrace := api.Add(isSynchronous, isLogOnly)
		changesModel := api.Add(isSynchronous, isModelOnly)

		// Goal 2: SYNC/LOG moves reproduce and consume the next private event.
		nextTraceActivity := frontend.Variable(0)
		for eventIndex := 0; eventIndex < MaxTraceEvents; eventIndex++ {
			isCurrentEvent := api.IsZero(api.Sub(tracePosition, eventIndex))
			nextTraceActivity = api.Add(nextTraceActivity, api.Mul(isCurrentEvent, c.TraceEvents[eventIndex]))
		}
		api.AssertIsEqual(api.Mul(consumesTrace, api.Sub(c.AlignmentActivities[moveIndex], nextTraceActivity)), 0)

		// Goal 3: SYNC/MODEL selects exactly one legal real-model transition.
		selectedTransitions := make([]frontend.Variable, TransitionCount)
		selectedTransitionCount := frontend.Variable(0)
		selectedLabel := frontend.Variable(0)
		selectedModelMoveCost := frontend.Variable(0)
		// The transition ID is private. Equality selectors act as a constrained
		// lookup into the fixed 35-transition public model.
		for transitionOffset := 0; transitionOffset < TransitionCount; transitionOffset++ {
			transitionID := transitionOffset + 1
			isSelected := api.IsZero(api.Sub(c.ModelTransitionIDs[moveIndex], transitionID))
			selectedTransitions[transitionOffset] = isSelected
			selectedTransitionCount = api.Add(selectedTransitionCount, isSelected)
			selectedLabel = api.Add(selectedLabel, api.Mul(isSelected, sepsisTransitionLabels[transitionOffset]))
			selectedModelMoveCost = api.Add(selectedModelMoveCost, api.Mul(isSelected, sepsisTransitionModelCosts[transitionOffset]))
		}
		api.AssertIsEqual(selectedTransitionCount, changesModel)
		api.AssertIsEqual(api.Mul(api.Sub(1, changesModel), c.ModelTransitionIDs[moveIndex]), 0)
		// On SYNC, the model transition label must equal the patient event.
		// Silent transitions have label 0, so they cannot be used as SYNC.
		api.AssertIsEqual(api.Mul(isSynchronous, api.Sub(selectedLabel, c.AlignmentActivities[moveIndex])), 0)
		api.AssertIsEqual(api.Mul(api.Add(isModelOnly, isPadding), c.AlignmentActivities[moveIndex]), 0)

		// Fire the selected transition using sparse per-place incidence lists.
		// This is the circuit form of:
		// next marking = old marking - transition inputs + outputs.
		for placeIndex := 0; placeIndex < PlaceCount; placeIndex++ {
			selectedInputArc := frontend.Variable(0)
			for _, transitionOffset := range sepsisInputTransitionsByPlace[placeIndex] {
				selectedInputArc = api.Add(selectedInputArc, selectedTransitions[transitionOffset])
			}
			selectedOutputArc := frontend.Variable(0)
			for _, transitionOffset := range sepsisOutputTransitionsByPlace[placeIndex] {
				selectedOutputArc = api.Add(selectedOutputArc, selectedTransitions[transitionOffset])
			}
			// An input arc requires an existing token. Therefore this constraint
			// rejects transitions that are not enabled in the current marking.
			api.AssertIsEqual(api.Mul(selectedInputArc, api.Sub(1, marking[placeIndex])), 0)
			nextMarking := api.Add(api.Sub(marking[placeIndex], selectedInputArc), selectedOutputArc)
			api.AssertIsBoolean(nextMarking)
			marking[placeIndex] = nextMarking
		}

		tracePosition = api.Add(tracePosition, consumesTrace)
		// Unit policy: SYNC and silent MODEL cost 0; LOG and visible MODEL
		// deviations cost 1. The prover cannot supply an arbitrary total.
		totalCost = api.Add(totalCost, isLogOnly, api.Mul(isModelOnly, selectedModelMoveCost))
	}

	// Goal 4: consume the complete trace and reach the exact final marking.
	api.AssertIsEqual(activeAlignmentMoves, c.AlignmentLength)
	api.AssertIsEqual(tracePosition, c.TraceLength)
	for placeIndex := 0; placeIndex < PlaceCount; placeIndex++ {
		api.AssertIsEqual(marking[placeIndex], sepsisFinalMarking[placeIndex])
	}

	// Goal 5: derive cost from moves. Goal 6: enforce the public threshold.
	api.AssertIsEqual(totalCost, c.AlignmentCost)
	api.AssertIsLessOrEqual(totalCost, c.CostThreshold)
	return nil
}
