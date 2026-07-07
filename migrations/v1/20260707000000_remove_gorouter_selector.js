exports.migrate = function(input) {
  // GoRouter route registration was removed in 1.2.1 (required the TAS/cf
  // tile, which is no longer installed on this foundation). Drop the stored
  // selector value so upgrades don't carry an orphaned property.
  delete input.properties['.properties.gorouter_selector'];
  return input;
};
