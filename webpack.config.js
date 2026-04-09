const path = require('path');

const isProduction = process.env.NODE_ENV === 'production';

module.exports = {
  mode: isProduction ? 'production' : 'development',
  devtool: isProduction ? 'source-map' : 'eval-source-map',
  entry: {
    common: "./static/js/dev/common.js",
    mobile: "./static/js/dev/mobile.js",
    keywordSelection: "./static/js/dev/keywordSelection.js",
  },
  output: {
    filename: "[name].bundle.js",
    path: path.resolve(__dirname, "static/js/dist"),
    clean: true,
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
  optimization: {
    minimize: isProduction,
  },
};
