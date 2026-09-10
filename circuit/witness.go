package circuit

import (
	"encoding/json"
	"fmt"
	"math/big"
	"os"
)

type savedAlignmentMove struct {
	Type            string `json:"type"`
	LogActivityID   int    `json:"log_activity_id"`
	TransitionIndex int    `json:"transition_index"`
	ReferenceCost   int    `json:"reference_cost"`
}

type savedAlignmentWitness struct {
	CaseID                  string               `json:"case_id"`
	TraceIndex              int                  `json:"trace_index"`
	PrivateTraceActivityIDs []int                `json:"private_trace_activity_ids"`
	PrivateTraceSalt        string               `json:"private_trace_salt"`
	CandidateAlignment      []savedAlignmentMove `json:"candidate_alignment"`
	DerivedUnitCost         int                  `json:"derived_unit_cost"`
}

// WitnessSummary contains non-secret metadata used for console reporting.
type WitnessSummary struct {
	CaseID          string
	TraceIndex      int
	TraceLength     int
	AlignmentLength int
	AlignmentCost   int
	CostThreshold   int
}

// LoadRealAlignmentAssignment converts one PM4Py alignment into a gnark
// assignment. Saved pre/post markings are deliberately ignored: the circuit
// recomputes every marking from the fixed Petri net.
func LoadRealAlignmentAssignment(path, recordsPath, caseID string, costThreshold int) (*SingleTracePetriNetCircuit, WitnessSummary, error) {
	contents, err := os.ReadFile(path)
	if err != nil {
		return nil, WitnessSummary{}, fmt.Errorf("read alignment witnesses: %w", err)
	}
	var saved []savedAlignmentWitness
	if err := json.Unmarshal(contents, &saved); err != nil {
		return nil, WitnessSummary{}, fmt.Errorf("decode alignment witnesses: %w", err)
	}

	var selected *savedAlignmentWitness
	for index := range saved {
		if saved[index].CaseID == caseID {
			selected = &saved[index]
			break
		}
	}
	if selected == nil {
		return nil, WitnessSummary{}, fmt.Errorf("case %q not found", caseID)
	}
	if len(selected.PrivateTraceActivityIDs) > MaxTraceEvents {
		return nil, WitnessSummary{}, fmt.Errorf("case %s has %d events; circuit maximum is %d", caseID, len(selected.PrivateTraceActivityIDs), MaxTraceEvents)
	}
	if len(selected.CandidateAlignment) > MaxAlignmentMoves {
		return nil, WitnessSummary{}, fmt.Errorf("case %s has %d alignment moves; circuit maximum is %d", caseID, len(selected.CandidateAlignment), MaxAlignmentMoves)
	}
	if costThreshold < 0 {
		return nil, WitnessSummary{}, fmt.Errorf("cost threshold cannot be negative")
	}

	traceSalt, ok := new(big.Int).SetString(selected.PrivateTraceSalt, 16)
	if !ok {
		return nil, WitnessSummary{}, fmt.Errorf("case %s has an invalid hexadecimal trace salt", caseID)
	}
	var integerTrace [MaxTraceEvents]int
	assignment := &SingleTracePetriNetCircuit{
		TraceLength:     len(selected.PrivateTraceActivityIDs),
		TraceSalt:       traceSalt,
		AlignmentLength: len(selected.CandidateAlignment),
		AlignmentCost:   selected.DerivedUnitCost,
		CostThreshold:   costThreshold,
	}
	for index := 0; index < MaxTraceEvents; index++ {
		assignment.TraceEvents[index] = 0
	}
	for index := 0; index < MaxAlignmentMoves; index++ {
		assignment.AlignmentMoveTypes[index] = MovePadding
		assignment.AlignmentActivities[index] = 0
		assignment.ModelTransitionIDs[index] = 0
	}
	for index, activityID := range selected.PrivateTraceActivityIDs {
		if activityID < 1 || activityID > ActivityCount {
			return nil, WitnessSummary{}, fmt.Errorf("case %s has invalid activity ID %d", caseID, activityID)
		}
		integerTrace[index] = activityID
		assignment.TraceEvents[index] = activityID
	}

	recomputedCost := 0
	for index, move := range selected.CandidateAlignment {
		switch move.Type {
		case "SYNC":
			assignment.AlignmentMoveTypes[index] = MoveSynchronous
			assignment.AlignmentActivities[index] = move.LogActivityID
			assignment.ModelTransitionIDs[index] = move.TransitionIndex
		case "LOG":
			assignment.AlignmentMoveTypes[index] = MoveLogOnly
			assignment.AlignmentActivities[index] = move.LogActivityID
			recomputedCost++
		case "MODEL":
			assignment.AlignmentMoveTypes[index] = MoveModelOnly
			assignment.ModelTransitionIDs[index] = move.TransitionIndex
			if move.TransitionIndex < 1 || move.TransitionIndex > TransitionCount {
				return nil, WitnessSummary{}, fmt.Errorf("case %s has invalid transition ID %d", caseID, move.TransitionIndex)
			}
			recomputedCost += sepsisTransitionModelCosts[move.TransitionIndex-1]
		default:
			return nil, WitnessSummary{}, fmt.Errorf("case %s has unknown move type %q", caseID, move.Type)
		}
	}
	if recomputedCost != selected.DerivedUnitCost {
		return nil, WitnessSummary{}, fmt.Errorf("saved cost %d does not match recomputed cost %d", selected.DerivedUnitCost, recomputedCost)
	}

	assignment.TraceCommitment = ComputeTraceCommitment(len(selected.PrivateTraceActivityIDs), integerTrace, traceSalt)
	merkleProof, err := loadCircuitMerkleProof(recordsPath, uint32(selected.TraceIndex))
	if err != nil {
		return nil, WitnessSummary{}, err
	}
	assignment.TraceIndex = selected.TraceIndex
	assignment.EventLogRoot = merkleProof.Root
	for level := 0; level < MerkleTreeDepth; level++ {
		assignment.MerklePath[level] = merkleProof.Siblings[level]
	}
	summary := WitnessSummary{
		CaseID:          selected.CaseID,
		TraceIndex:      selected.TraceIndex,
		TraceLength:     len(selected.PrivateTraceActivityIDs),
		AlignmentLength: len(selected.CandidateAlignment),
		AlignmentCost:   selected.DerivedUnitCost,
		CostThreshold:   costThreshold,
	}
	return assignment, summary, nil
}
