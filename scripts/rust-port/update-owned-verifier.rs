//! Disposable process-tree fixture. This does not verify signatures.
use std::{
    env, fs::OpenOptions, io::Write, path::PathBuf, process::Command, thread, time::Duration,
};

fn main() {
    let mode = env::args().nth(1).expect("explicit fixture mode required");
    if mode == "cosign-child" {
        let ready = PathBuf::from(
            env::var_os("UPDATE_CANCEL_VERIFIER_READY").expect("private readiness path"),
        );
        let root = env::temp_dir()
            .canonicalize()
            .expect("private temporary root");
        let parent = ready
            .parent()
            .expect("readiness parent")
            .canonicalize()
            .expect("owned existing parent");
        assert!(
            parent.starts_with(root),
            "readiness escapes disposable TMPDIR"
        );
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options
            .open(&ready)
            .expect("exclusive owned readiness file");
        write!(file, "{}", std::process::id()).expect("write native child PID");
        drop(file);
        loop {
            thread::sleep(Duration::from_secs(1));
        }
    }
    assert_eq!(
        mode, "verify-blob",
        "fixture only accepts test verifier invocation"
    );
    let mut child = Command::new(env::current_exe().expect("native fixture executable"))
        .arg("cosign-child")
        .spawn()
        .expect("owned native child");
    let _ = child.wait().expect("reap owned child");
}
