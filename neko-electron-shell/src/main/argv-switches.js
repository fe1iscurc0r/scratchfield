'use strict';

function switchNameFromArg(arg) {
  if (typeof arg !== 'string' || !arg.startsWith('--')) return '';
  return arg.slice(2).split('=')[0];
}

function stripSwitches(args, names, valueTakingNames = []) {
  const blocked = new Set(names);
  const valueTaking = new Set(valueTakingNames);
  const result = [];

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    const name = switchNameFromArg(arg);
    if (!name || !blocked.has(name)) {
      result.push(arg);
      continue;
    }

    if (valueTaking.has(name) && !String(arg).includes('=') && i + 1 < args.length) {
      const nextArg = args[i + 1];
      if (typeof nextArg === 'string' && !nextArg.startsWith('--')) {
        i += 1;
      }
    }
  }

  return result;
}

function collectSwitchValues(args, name) {
  const values = [];
  const switchPrefix = `--${name}`;

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (typeof arg !== 'string') continue;
    if (arg.startsWith(`${switchPrefix}=`)) {
      values.push(arg.slice(switchPrefix.length + 1));
      continue;
    }
    if (arg === switchPrefix && i + 1 < args.length) {
      const nextArg = args[i + 1];
      if (typeof nextArg === 'string' && !nextArg.startsWith('--')) {
        values.push(nextArg);
        i += 1;
      }
    }
  }

  return values;
}

function mergeCommaSeparatedSwitchValues(values, requiredValues = []) {
  const merged = [];
  const seen = new Set();
  const addValue = (value) => {
    String(value || '').split(',').forEach((part) => {
      const feature = part.trim();
      if (!feature || seen.has(feature)) return;
      seen.add(feature);
      merged.push(feature);
    });
  };

  values.forEach(addValue);
  requiredValues.forEach(addValue);
  return merged.join(',');
}

module.exports = {
  collectSwitchValues,
  mergeCommaSeparatedSwitchValues,
  stripSwitches,
};
