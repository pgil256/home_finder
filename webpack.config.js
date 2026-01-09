const path = require('path');

module.exports = {
  mode: "development",
  entry: {
    common: "./static/js/dev/common.js",
    mobile: "./static/js/dev/mobile.js",
    keywordSelection: "./static/js/dev/keywordSelection.js",
  },
  output: {
    filename: "[name].bundle.js",
    path: path.resolve(__dirname, "static/js/dist"),
  },
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: {
          loader: "babel-loader",
          options: {
            presets: ["@babel/preset-env"],
          },
        },
      },
    ],
  },
};
