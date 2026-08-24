const TEMPLATE_EXE_SEGMENTS = [
  "/resources/runtime/python/lib/venv/scripts/nt/",
  "/resources/runtime/python/lib/site-packages/setuptools/",
  "/resources/runtime/python/lib/site-packages/pip/_vendor/distlib/",
];

function shouldSkipSigning(filePath) {
  const normalized = filePath.replace(/\\/g, "/").toLowerCase();
  if (!normalized.endsWith(".exe")) {
    return false;
  }
  return TEMPLATE_EXE_SEGMENTS.some((segment) => normalized.includes(segment));
}

async function sign(configuration, packager) {
  if (shouldSkipSigning(configuration.path)) {
    console.log(`[win-sign] skip template exe: ${configuration.path}`);
    return;
  }

  const manager = await packager.signingManager.value;
  return manager.doSign(configuration, packager);
}

exports.sign = sign;
exports.default = sign;
