"""Original native hashes after separate raw/Git/official SDK reconstruction.

Review: docs/rust-port/evidence/update-frozen-registration-20261003.json.
Producer run 37141133260; these entries do not imply Rust acceptance.
"""

CAPTURE_SOURCE_COMMIT = "8670450fbd3bd4d57a4c737f29abec113dd8eb70"
ANCHORS = {
    "darwin-arm64": {
        "apply": "1bf8cb3ad42624b7a8d0a76421b5f560e2be30bbcffedf50637b000fd58a4541",
        "cache": "1e873fab161c41123075de189c125cf73f778fd85e0a98a91e8a95a7a6d16a94",
        "cancellation": "3095b027bb62535774018f4228cf1048e6f3720e087a43abb7f384b2d3e7aa83",
        "cosign": "9906b99ff46cf7a3dc809f36a93e8f45a98ddc9eb1b0c757fe5e7bff06933845",
        "persistence": "f4c3e34c08b95b1abbdeb0588441fa703087b03da42c2c60378765b6ca768f13",
        "request": "674861839bf4660ef9551acfc8498e12583ad7096cb3c3f66406e35bb476f8c1"
    },
    "linux-amd64": {
        "apply": "ddd0626731e5bf60dea3e966241f54a3067986360f86fb1cfcd587e8f3eb8b38",
        "cache": "cc5c185a50c2b262979609d733cb01d51a16149a8c68fcaa4c0a583f40e2f7e3",
        "cancellation": "dbc850b991a6d4ca35abecb599fcd175c1376e134d5fdc3437696be429744a1b",
        "cosign": "c266f7a26adb17c9df1aa347000abbcb4e2346ce252c5b2dab5714025fb0e370",
        "persistence": "cbc95f8835c685c13572aaa32b241895cc7105c18f71d4a3f3a5fe628eacea4e",
        "request": "f017b8b6a233365f51ec0a81b0c9097bc157b570e77a3bcd100b0c4e7c17332d"
    },
    "windows-amd64": {
        "apply": "bd92e74e890e148a3e9275dac40057b0534bf8bf00a51504c0802a62726951fd",
        "cache": "e0df86ff3db802e15b07c838f5126305f70a00bb98be830ce0b8eb478e14738a",
        "cancellation": "92793df27226cd9ff71db1337bc552ba9d2d5ca4e43beac44e32af83a951f934",
        "cosign": "ca19515b2ac21e01f53b049131ad0be2694d55e711eeacb30df7ac03518f2a14",
        "persistence": "1e32f9b7683a29c5cac130e40141dfb52dc58534f29ef8c1651b665175e25763",
        "request": "a68e8ed42f86a6d355f964bc8c416efcf2a85e269fdef89ac178e81dceea7710",
    },
}

# Exact independently reviewable module-only compatibility receipt; this does
# not alter the historical native-v1 capture anchors above.
UPDATE_MODULE_COMPATIBILITY_RECEIPT_SHA256 = "3f968174b40240f895876c6e181b64abfda73fbe2e517455be6c5ff737c2b7a8"
