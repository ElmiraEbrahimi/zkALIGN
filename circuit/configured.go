package circuit

import (
	"fmt"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
)

// ConfiguredCircuit uses one fixed public configuration per compilation. Config
// is never a witness and cannot be selected by the prover after setup.
type ConfiguredCircuit struct {
	TraceCommitment     frontend.Variable `gnark:",public"`
	EventLogRoot        frontend.Variable `gnark:",public"`
	CostThreshold       frontend.Variable `gnark:",public"`
	AlignmentCost       frontend.Variable
	TraceLength         frontend.Variable
	TraceEvents         []frontend.Variable
	TraceSalt           frontend.Variable
	TraceIndex          frontend.Variable
	MerklePath          [MerkleTreeDepth]frontend.Variable
	AlignmentLength     frontend.Variable
	AlignmentMoveTypes  []frontend.Variable
	AlignmentActivities []frontend.Variable
	ModelTransitionIDs  []frontend.Variable
	Config              *ModelConfig `gnark:"-"`
}

func (c *ConfiguredCircuit) Define(api frontend.API) error {
	if err := c.Config.Validate(); err != nil {
		return err
	}
	if len(c.TraceEvents) != c.Config.TraceCapacity || len(c.AlignmentMoveTypes) != c.Config.AlignmentCapacity || len(c.AlignmentActivities) != c.Config.AlignmentCapacity || len(c.ModelTransitionIDs) != c.Config.AlignmentCapacity {
		return fmt.Errorf("witness dimensions differ from configuration")
	}
	cfg := c.Config
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
	for eventIndex := 0; eventIndex < cfg.TraceCapacity; eventIndex++ {
		traceHash.Write(c.TraceEvents[eventIndex])
		// knownActivity becomes 1 exactly when the slot is one of activity IDs
		// 1..ActivityCount. Together with padding, this rejects other values.
		knownActivity := frontend.Variable(0)
		for activityID := 1; activityID <= cfg.ActivityCount; activityID++ {
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
	marking := make([]frontend.Variable, len(cfg.Initial))
	activeAlignmentMoves := frontend.Variable(0)
	previousMovePadding := frontend.Variable(0)
	for placeIndex := 0; placeIndex < len(cfg.Initial); placeIndex++ {
		marking[placeIndex] = cfg.Initial[placeIndex]
	}

	for moveIndex := 0; moveIndex < cfg.AlignmentCapacity; moveIndex++ {
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
		for eventIndex := 0; eventIndex < cfg.TraceCapacity; eventIndex++ {
			isCurrentEvent := api.IsZero(api.Sub(tracePosition, eventIndex))
			nextTraceActivity = api.Add(nextTraceActivity, api.Mul(isCurrentEvent, c.TraceEvents[eventIndex]))
		}
		api.AssertIsEqual(api.Mul(consumesTrace, api.Sub(c.AlignmentActivities[moveIndex], nextTraceActivity)), 0)

		// Goal 3: SYNC/MODEL selects exactly one legal real-model transition.
		selectedTransitions := make([]frontend.Variable, len(cfg.Labels))
		selectedTransitionCount := frontend.Variable(0)
		selectedLabel := frontend.Variable(0)
		selectedModelMoveCost := frontend.Variable(0)
		// The transition ID is private. Equality selectors act as a constrained
		// lookup into the fixed public model for this compiled configuration.
		for transitionOffset := 0; transitionOffset < len(cfg.Labels); transitionOffset++ {
			transitionID := transitionOffset + 1
			isSelected := api.IsZero(api.Sub(c.ModelTransitionIDs[moveIndex], transitionID))
			selectedTransitions[transitionOffset] = isSelected
			selectedTransitionCount = api.Add(selectedTransitionCount, isSelected)
			selectedLabel = api.Add(selectedLabel, api.Mul(isSelected, cfg.Labels[transitionOffset]))
			selectedModelMoveCost = api.Add(selectedModelMoveCost, api.Mul(isSelected, cfg.ModelCosts[transitionOffset]))
		}
		api.AssertIsEqual(selectedTransitionCount, changesModel)
		api.AssertIsEqual(api.Mul(api.Sub(1, changesModel), c.ModelTransitionIDs[moveIndex]), 0)
		// On SYNC, the model transition label must equal the trace event.
		// Silent transitions have label 0, so they cannot be used as SYNC.
		api.AssertIsEqual(api.Mul(isSynchronous, api.Sub(selectedLabel, c.AlignmentActivities[moveIndex])), 0)
		api.AssertIsEqual(api.Mul(api.Add(isModelOnly, isPadding), c.AlignmentActivities[moveIndex]), 0)

		// Fire the selected transition using sparse per-place incidence lists.
		// This is the circuit form of:
		// next marking = old marking - transition inputs + outputs.
		for placeIndex := 0; placeIndex < len(cfg.Initial); placeIndex++ {
			selectedInputArc := frontend.Variable(0)
			for _, transitionOffset := range cfg.Inputs[placeIndex] {
				selectedInputArc = api.Add(selectedInputArc, selectedTransitions[transitionOffset])
			}
			selectedOutputArc := frontend.Variable(0)
			for _, transitionOffset := range cfg.Outputs[placeIndex] {
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
	for placeIndex := 0; placeIndex < len(cfg.Initial); placeIndex++ {
		api.AssertIsEqual(marking[placeIndex], cfg.Final[placeIndex])
	}

	// Goal 5: derive cost from moves. Goal 6: enforce the public threshold.
	api.AssertIsEqual(totalCost, c.AlignmentCost)
	api.AssertIsLessOrEqual(totalCost, c.CostThreshold)
	return nil
}
