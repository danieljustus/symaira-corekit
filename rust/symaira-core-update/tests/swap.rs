use serde::Deserialize;
use std::fs;
use std::path::{Path, PathBuf};
use symaira_core_update::apply::{BinaryValidator, atomic_swap};

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    input: Input,
    observation: Observation,
}

#[derive(Deserialize)]
struct Input {
    id: String,
    initial: String,
    source: String,
    backup: String,
    reject: bool,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
struct Observation {
    error: bool,
    target_exists: bool,
    target_content: String,
    source_exists: bool,
    backup_exists: bool,
    validator_saw_target: bool,
    validator_saw_backup: bool,
    validator_saw_content: String,
    remaining_file_names: Vec<String>,
}

#[test]
fn atomic_swap_failure_and_rollback_match_go() {
    let path = std::env::var_os("UPDATE_SWAP_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../testdata/rust-port/fixtures/update/swap.json")
        });
    let fixture: Fixture = serde_json::from_slice(&fs::read(path).expect("read Go swap fixture"))
        .expect("parse Go swap fixture");
    assert_eq!(fixture.cases.len(), 4);
    let mut ids = Vec::new();
    for (index, case) in fixture.cases.into_iter().enumerate() {
        ids.push(case.input.id.clone());
        let root = std::env::temp_dir().join(format!(
            "corekit-swap-{}-{index}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("system clock")
                .as_nanos()
        ));
        fs::create_dir(&root).expect("create private swap root");
        let target = root.join("mytool");
        let staged = root.join("staged");
        let backup = root.join("mytool.bak");
        if !case.input.initial.is_empty() {
            fs::write(&target, &case.input.initial).expect("seed old target");
        }
        if !case.input.source.is_empty() {
            fs::write(&staged, &case.input.source).expect("seed staged target");
        }
        if !case.input.backup.is_empty() {
            fs::write(&backup, &case.input.backup).expect("seed stale backup");
        }
        let mut saw_target = false;
        let mut saw_backup = false;
        let mut saw_content = String::new();
        let mut validator = |path: &Path| {
            saw_target = path == target;
            saw_backup = backup.exists();
            saw_content = fs::read_to_string(path).expect("validator reads new target");
            Err("reject installed binary".to_owned())
        };
        let check: Option<BinaryValidator<'_>> = if case.input.reject {
            Some(&mut validator)
        } else {
            None
        };
        let error = atomic_swap(&staged, &target, check).is_err();
        let mut names: Vec<_> = fs::read_dir(&root)
            .expect("read swap root")
            .map(|entry| {
                entry
                    .expect("read entry")
                    .file_name()
                    .to_string_lossy()
                    .into_owned()
            })
            .collect();
        names.sort();
        let actual = Observation {
            error,
            target_exists: target.exists(),
            target_content: fs::read_to_string(&target).unwrap_or_default(),
            source_exists: staged.exists(),
            backup_exists: backup.exists(),
            validator_saw_target: saw_target,
            validator_saw_backup: saw_backup,
            validator_saw_content: saw_content,
            remaining_file_names: names,
        };
        assert_eq!(actual, case.observation, "{} observation", case.input.id);
        fs::remove_dir_all(root).expect("remove owned swap root");
    }
    ids.sort();
    assert_eq!(
        ids,
        [
            "missing-source",
            "preexisting-backup",
            "validation-first-install",
            "validation-rollback"
        ]
    );
}
