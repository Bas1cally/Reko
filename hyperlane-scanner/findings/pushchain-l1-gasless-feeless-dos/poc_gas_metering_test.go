package vm

import (
	"math/big"

	"github.com/ethereum/go-ethereum/common"

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

	// The core claim: cosmos gas charged is far below the EVM gas actually burned.
	// If this holds, the EVM computational cost is invisible to the cosmos block meter.
	s.T().Logf(">>> RATIO balanceOf: EVM/cosmos = %.1fx", float64(res.GasUsed)/float64(max1(callCosmosDelta)))
	s.T().Logf(">>> RATIO deploy:    EVM/cosmos = %.1fx", float64(resDeploy.GasUsed)/float64(max1(deployCosmosDelta)))
}

func max1(x uint64) uint64 {
	if x == 0 {
		return 1
	}
	return x
}
