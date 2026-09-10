package circuit

import (
	"hash"
	"math/big"

	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	frMiMC "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
)

// ComputeTraceCommitment mirrors the field-element sequence hashed in Define.
func ComputeTraceCommitment(traceLength int, trace [MaxTraceEvents]int, salt *big.Int) *big.Int {
	values := []*big.Int{big.NewInt(DomainTraceV2), big.NewInt(int64(traceLength))}
	for _, activity := range trace {
		values = append(values, big.NewInt(int64(activity)))
	}
	values = append(values, salt)
	return hashFieldElements(values...)
}

func hashFieldElements(values ...*big.Int) *big.Int {
	var fieldHash hash.Hash = frMiMC.NewMiMC()
	for _, value := range values {
		var element fr.Element
		element.SetBigInt(value)
		bytes := element.Bytes()
		_, _ = fieldHash.Write(bytes[:])
	}
	return new(big.Int).SetBytes(fieldHash.Sum(nil))
}
