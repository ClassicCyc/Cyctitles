# Override for the upstream hook, which calls copy_metadata('webrtcvad') and
# fails when the package is installed as "webrtcvad-wheels". webrtcvad is a
# self-contained extension module, so no extra data/metadata is needed.

datas = []
binaries = []
hiddenimports = []
