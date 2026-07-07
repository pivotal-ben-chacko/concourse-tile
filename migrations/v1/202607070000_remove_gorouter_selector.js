exports.migrate = function(input) {
  // GoRouter route registration was removed in 1.2.1 (required the TAS/cf
  // tile, which is no longer installed on this foundation). Drop the stored
  // selector value AND its nested option properties — Ops Manager rejects a
  // migration result holding option properties whose parent selector is gone.
  Object.keys(input.properties).forEach(function(key) {
    if (key.indexOf('.properties.gorouter_selector') === 0) {
      delete input.properties[key];
    }
  });
  return input;
};
