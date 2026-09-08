package circuit

import (
	"hash"
	"math/big"

	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	frMiMC "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
)

// TraceCommitment mirrors the field-element sequence hashed in Define.
func TraceCommitment(traceLength int, trace [MaxTrace]int, salt int) *big.Int {
	var h hash.Hash = frMiMC.NewMiMC()
	writeElement := func(value int) {
		var element fr.Element
		element.SetInt64(int64(value))
		bytes := element.Bytes()
		_, _ = h.Write(bytes[:])
	}
	writeElement(DomainTraceV1)
	writeElement(traceLength)
	for _, activity := range trace {
		writeElement(activity)
	}
	writeElement(salt)
	return new(big.Int).SetBytes(h.Sum(nil))
}
