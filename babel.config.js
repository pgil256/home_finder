// Single Babel config shared by both toolchains:
//   • webpack (babel-loader) builds the browser bundles → default browserslist targets
//   • Jest (babel-jest) runs the specs in Node → transpile down to the current Node
// babel-jest runs with env "test", so only then do we target Node.
module.exports = (api) => {
  const forNode = api.env('test');
  return {
    presets: [
      ['@babel/preset-env', forNode ? { targets: { node: 'current' } } : {}],
    ],
  };
};
