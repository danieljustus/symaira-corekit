use std::fs;
use symaira_core_update::extract::observe;

#[test]
fn preexisting_extract_root_is_never_deleted() {
    let root =
        std::env::temp_dir().join(format!("symaira-update-extract-{}-0", std::process::id()));
    fs::create_dir(&root).expect("reserve owned extract root");
    let sentinel = root.join("keep");
    fs::write(&sentinel, b"preserve me").expect("seed owned sentinel");

    let observation = observe("tar.gz", b"", "mytool");
    let preserved = fs::read(&sentinel);
    fs::remove_dir_all(&root).expect("remove owned test root");

    assert_eq!(observation.error.expect("existing root refused").code, "io");
    assert_eq!(preserved.expect("existing data preserved"), b"preserve me");
}
