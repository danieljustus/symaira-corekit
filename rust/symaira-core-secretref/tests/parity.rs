#![deny(unsafe_code)]

#[test]
fn corpus_has_all_contract_rows_and_pinned_provenance() {
    let corpus = include_str!("../../../testdata/rust-port/fixtures/fs-secret/corpus.json");
    assert!(corpus.contains("f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"));
    for id in [
        "FS-001", "FS-002", "FS-003", "FS-004", "FS-005", "FS-006", "FS-007", "SEC-001", "SEC-002",
        "SEC-003", "SEC-004", "SEC-005", "SEC-006",
    ] {
        assert!(corpus.contains(id), "corpus missing {id}");
    }
}

#[test]
fn secret_contract_is_byte_identical_to_go_contract() {
    let rust = include_bytes!("../contracts/secret_refs.json");
    let go = include_bytes!("../../../contracts/secret_refs.json");
    assert_eq!(rust, go);
}
