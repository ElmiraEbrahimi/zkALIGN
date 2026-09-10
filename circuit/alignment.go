package circuit

import (
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
)

const (
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
	MovePadding = iota
	MoveSynchronous
	MoveLogOnly
	MoveModelOnly
)

// SingleTracePetriNetCircuit proves that one private healthcare trace has a
// valid, complete alignment against the fixed public Sepsis Petri net.
type SingleTracePetriNetCircuit struct {
	TraceCommitment frontend.Variable `gnark:",public"`
	EventLogRoot    frontend.Variable `gnark:",public"`
	CostThreshold   frontend.Variable `gnark:",public"`
	AlignmentCost   frontend.Variable `gnark:",public"`

	TraceLength frontend.Variable
	TraceEvents [MaxTraceEvents]frontend.Variable
	TraceSalt   frontend.Variable
	TraceIndex  frontend.Variable
	MerklePath  [MerkleTreeDepth]frontend.Variable

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
	traceHash.Write(DomainTraceV2, c.TraceLength)
	usedTraceEvents := frontend.Variable(0)
	previousTracePadding := frontend.Variable(0)
	for eventIndex := 0; eventIndex < MaxTraceEvents; eventIndex++ {
		traceHash.Write(c.TraceEvents[eventIndex])
		knownActivity := frontend.Variable(0)
		for activityID := 1; activityID <= ActivityCount; activityID++ {
			knownActivity = api.Add(knownActivity, api.IsZero(api.Sub(c.TraceEvents[eventIndex], activityID)))
		}
		isTracePadding := api.IsZero(c.TraceEvents[eventIndex])
		api.AssertIsEqual(api.Add(knownActivity, isTracePadding), 1)
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
	marking := make([]frontend.Variable, PlaceCount)
	activeAlignmentMoves := frontend.Variable(0)
	previousMovePadding := frontend.Variable(0)
	for placeIndex := 0; placeIndex < PlaceCount; placeIndex++ {
		marking[placeIndex] = sepsisInitialMarking[placeIndex]
	}

	for moveIndex := 0; moveIndex < MaxAlignmentMoves; moveIndex++ {
		isPadding := api.IsZero(c.AlignmentMoveTypes[moveIndex])
		isSynchronous := api.IsZero(api.Sub(c.AlignmentMoveTypes[moveIndex], MoveSynchronous))
		isLogOnly := api.IsZero(api.Sub(c.AlignmentMoveTypes[moveIndex], MoveLogOnly))
		isModelOnly := api.IsZero(api.Sub(c.AlignmentMoveTypes[moveIndex], MoveModelOnly))
		api.AssertIsEqual(api.Add(isPadding, isSynchronous, isLogOnly, isModelOnly), 1)

		isActiveMove := api.Sub(1, isPadding)
		api.AssertIsEqual(api.Mul(previousMovePadding, isActiveMove), 0)
		previousMovePadding = isPadding
		activeAlignmentMoves = api.Add(activeAlignmentMoves, isActiveMove)
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
		api.AssertIsEqual(api.Mul(isSynchronous, api.Sub(selectedLabel, c.AlignmentActivities[moveIndex])), 0)
		api.AssertIsEqual(api.Mul(api.Add(isModelOnly, isPadding), c.AlignmentActivities[moveIndex]), 0)

		// Fire the selected transition using sparse per-place incidence lists.
		for placeIndex := 0; placeIndex < PlaceCount; placeIndex++ {
			selectedInputArc := frontend.Variable(0)
			for _, transitionOffset := range sepsisInputTransitionsByPlace[placeIndex] {
				selectedInputArc = api.Add(selectedInputArc, selectedTransitions[transitionOffset])
			}
			selectedOutputArc := frontend.Variable(0)
			for _, transitionOffset := range sepsisOutputTransitionsByPlace[placeIndex] {
				selectedOutputArc = api.Add(selectedOutputArc, selectedTransitions[transitionOffset])
			}
			api.AssertIsEqual(api.Mul(selectedInputArc, api.Sub(1, marking[placeIndex])), 0)
			nextMarking := api.Add(api.Sub(marking[placeIndex], selectedInputArc), selectedOutputArc)
			api.AssertIsBoolean(nextMarking)
			marking[placeIndex] = nextMarking
		}

		tracePosition = api.Add(tracePosition, consumesTrace)
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
