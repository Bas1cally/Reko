package vm

import (
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/crypto"

	"github.com/cosmos/evm/contracts"
	testconstants "github.com/cosmos/evm/testutil/constants"
)

// TestPoCDerivedCallCosmosGasNotMetered measures whether the EVM gas consumed by a
// DerivedEVMCall is charged back to the *cosmos* block gas meter of the surrounding
// context. Push Chain's gasless MsgExecutePayload path (x/uexecutor) triggers derived
// EVM work while the outer cosmos tx pays no fee and declares its own (small) cosmos
// gas. If the EVM compute is NOT reflected in ctx.GasMeter(), then the cosmos block
// gas limit does not bound how many such txs fit per block -> feeless CPU-amplification.
//
// Reports res.GasUsed (EVM gas) vs the cosmos ctx.GasMeter() delta for:
//   (1) a cheap call (balanceOf)
//   (2) a heavy op (contract deployment, ~1M+ EVM gas)
func (s *KeeperTestSuite) TestPoCDerivedCallCosmosGasNotMetered() {
	s.SetupTest()
	ctx := s.Network.GetContext()
	keeper := s.Network.App.GetEVMKeeper()
	from := s.Keyring.GetAddr(0)

	erc20ABI := contracts.ERC20MinterBurnerDecimalsContract.ABI
	wevmos := common.HexToAddress(testconstants.WEVMOSContractMainnet)

	// --- (1) cheap call: balanceOf ---
	callData, err := erc20ABI.Pack("balanceOf", from)
	s.Require().NoError(err)

	cosmosBefore := ctx.GasMeter().GasConsumed()
	res, err := keeper.DerivedEVMCallWithData(
		ctx, from, &wevmos, callData,
		true,  // commit
		false, // gasless
		false, // isModuleSender
		big.NewInt(0), big.NewInt(1_000_000), nil,
	)
	s.Require().NoError(err)
	cosmosAfterCall := ctx.GasMeter().GasConsumed()
	callCosmosDelta := cosmosAfterCall - cosmosBefore

	s.T().Logf("[balanceOf] EVM res.GasUsed=%d  cosmos ctx.GasMeter delta=%d", res.GasUsed, callCosmosDelta)

	// --- (2) heavy op: deploy the ERC20 contract (constructor: name, symbol, decimals) ---
	ctorArgs, err := erc20ABI.Pack("", "PoCToken", "POC", uint8(18))
	s.Require().NoError(err)
	deployData := append([]byte(contracts.ERC20MinterBurnerDecimalsContract.Bin), ctorArgs...)

	cosmosBeforeDeploy := ctx.GasMeter().GasConsumed()
	resDeploy, err := keeper.DerivedEVMCallWithData(
		ctx, from, nil, deployData,
		true,  // commit
		false, // gasless
		false, // isModuleSender
		big.NewInt(0), big.NewInt(5_000_000), nil,
	)
	s.Require().NoError(err)
	cosmosAfterDeploy := ctx.GasMeter().GasConsumed()
	deployCosmosDelta := cosmosAfterDeploy - cosmosBeforeDeploy

	s.T().Logf("[deploy]    EVM res.GasUsed=%d  cosmos ctx.GasMeter delta=%d", resDeploy.GasUsed, deployCosmosDelta)

	s.T().Logf(">>> [SUCCESS] balanceOf: EVM/cosmos = %.2fx (cosmos charged >= EVM => metered)", float64(res.GasUsed)/float64(max1(callCosmosDelta)))
	s.T().Logf(">>> [SUCCESS] deploy:    EVM/cosmos = %.2fx (cosmos charged >= EVM => metered)", float64(resDeploy.GasUsed)/float64(max1(deployCosmosDelta)))

	// --- (3) THE BUG: a compute-heavy, storage-light REVERT skips
	//         ctx.GasMeter().ConsumeGas(res.GasUsed). call_evm.go:
	//             if res.Failed() { return ... }              // <- returns here on OOG/revert
	//             ctx.GasMeter().ConsumeGas(res.GasUsed, ...)  // <- never reached on failure
	//         So the EVM COMPUTATIONAL gas burned by a reverted execution is invisible to the
	//         cosmos block gas meter. KV gas still applies, so we use a pure-compute loop
	//         (no storage) to isolate the effect.
	from1 := s.Keyring.GetAddr(1)

	// Deploy an infinite-loop contract: runtime = 5b600056 (JUMPDEST PUSH1 0 JUMP).
	// init code returns that 4-byte runtime.
	loopInit := common.FromHex("635b6000566000526004601cf3")
	nonce0 := keeper.GetNonce(ctx, from1)
	_, err = keeper.DerivedEVMCallWithData(
		ctx, from1, nil, loopInit,
		true, false, false, big.NewInt(0), big.NewInt(200_000), nil,
	)
	s.Require().NoError(err)
	loopAddr := crypto.CreateAddress(from1, nonce0)

	// Call the loop with a large gas limit -> runs out of gas (pure compute), reverts.
	const bigGas = 8_000_000
	cosmosBeforeRev := ctx.GasMeter().GasConsumed()
	resRev, errRev := keeper.DerivedEVMCallWithData(
		ctx, from1, &loopAddr, []byte{},
		true, false, false, big.NewInt(0), big.NewInt(bigGas), nil,
	)
	cosmosAfterRev := ctx.GasMeter().GasConsumed()
	revCosmosDelta := cosmosAfterRev - cosmosBeforeRev
	s.Require().Error(errRev)
	s.Require().True(resRev.Failed())

	s.T().Logf("[REVERT/OOG] EVM res.GasUsed=%d  cosmos ctx.GasMeter delta=%d", resRev.GasUsed, revCosmosDelta)
	s.T().Logf(">>> [REVERT/OOG] EVM burned %d gas; cosmos meter moved only %d => %d gas of EVM CPU went UNMETERED (free)",
		resRev.GasUsed, revCosmosDelta, int64(resRev.GasUsed)-int64(revCosmosDelta))

	s.Require().Less(revCosmosDelta, resRev.GasUsed/2,
		"BUG CONFIRMED: a reverted compute-heavy derived call charges the cosmos meter far LESS than the EVM CPU it burned")
}

func max1(x uint64) uint64 {
	if x == 0 {
		return 1
	}
	return x
}
