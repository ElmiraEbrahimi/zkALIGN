package circuit

import (
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/test"
	"math/big"
	"testing"
)

func TestConfiguredCommitmentMatchesLegacy(t *testing.T) {
	cfg := SepsisConfig()
	var trace [MaxTraceEvents]int
	trace[0] = 5
	a, err := ConfiguredCommitment(cfg, []int{5}, big.NewInt(17))
	if err != nil {
		t.Fatal(err)
	}
	if a.Cmp(ComputeTraceCommitment(1, trace, big.NewInt(17))) != 0 {
		t.Fatal("hash encoding changed")
	}
}
func TestConfiguredLoopAndPopulation(t *testing.T) {
	cfg := &ModelConfig{ActivityCount: 2, TraceCapacity: 4, AlignmentCapacity: 5,
		Initial: []int{1, 0}, Final: []int{0, 1}, Labels: []int{1, 2}, ModelCosts: []int{1, 1},
		Inputs: [][]int{{0, 1}, {}}, Outputs: [][]int{{0}, {1}}}
	cost := 0
	cases, _, _, err := PrepareConfiguredPopulation(cfg, []EvaluationCase{{CaseID: "loop", Index: 0, Events: []int{1, 1, 2}, Salt: "9", Cost: &cost, Status: "aligned",
		Moves: []EvaluationMove{{1, 1, 1}, {1, 1, 1}, {1, 2, 2}}}})
	if err != nil {
		t.Fatal(err)
	}
	a, err := cases[0].Assignment(cfg, 0)
	if err != nil {
		t.Fatal(err)
	}
	if err = test.IsSolved(NewConfiguredCircuit(cfg), a, ecc.BN254.ScalarField()); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*ConfiguredCircuit){
		"trace":      func(a *ConfiguredCircuit) { a.TraceEvents[0] = 2 },
		"path":       func(a *ConfiguredCircuit) { a.MerklePath[0] = 1 },
		"cost":       func(a *ConfiguredCircuit) { a.AlignmentCost = 1 },
		"completion": func(a *ConfiguredCircuit) { a.ModelTransitionIDs[2] = 1 },
		"padding":    func(a *ConfiguredCircuit) { a.AlignmentActivities[4] = 2 },
		"length":     func(a *ConfiguredCircuit) { a.AlignmentLength = 2 },
		"domain":     func(a *ConfiguredCircuit) { a.AlignmentMoveTypes[0] = 4 },
	} {
		t.Run(name, func(t *testing.T) {
			a, _ := cases[0].Assignment(cfg, 0)
			mutate(a)
			if test.IsSolved(NewConfiguredCircuit(cfg), a, ecc.BN254.ScalarField()) == nil {
				t.Fatal("invalid witness accepted")
			}
		})
	}
}
