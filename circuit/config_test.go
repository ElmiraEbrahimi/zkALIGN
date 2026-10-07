package circuit

import (
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/test"
	"testing"
)

func TestConfiguredSepsisMatchesLegacy(t *testing.T) {
	legacy, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &SingleTracePetriNetCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	configured, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, NewConfiguredCircuit(SepsisConfig()))
	if err != nil {
		t.Fatal(err)
	}
	if legacy.GetNbConstraints() != configured.GetNbConstraints() {
		t.Fatal("constraint count changed")
	}
	t.Logf("Sepsis constraints: %d", configured.GetNbConstraints())
	a := realCaseAssignment(t, 1).Configured()
	if err := test.IsSolved(NewConfiguredCircuit(SepsisConfig()), a, ecc.BN254.ScalarField()); err != nil {
		t.Fatal(err)
	}
	a.AlignmentCost = 0
	if err := test.IsSolved(NewConfiguredCircuit(SepsisConfig()), a, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("false cost accepted")
	}
}

func TestModelConfigValidation(t *testing.T) {
	for _, mutate := range []func(*ModelConfig){
		func(c *ModelConfig) { c.TraceCapacity = 0 },
		func(c *ModelConfig) { c.Labels[0] = 99 },
		func(c *ModelConfig) { c.ModelCosts[0] = 0 },
		func(c *ModelConfig) { c.Initial[0] = 2 },
		func(c *ModelConfig) { c.Inputs = [][]int{} },
	} {
		c := SepsisConfig()
		mutate(c)
		if c.Validate() == nil {
			t.Fatal("invalid config accepted")
		}
	}
}
