const withStyleX = require('@stylexswc/nextjs-plugin');
module.exports = withStyleX({rsOptions:{exclude:['**/node_modules/**']}})({
  poweredByHeader:false,
  // The generated theme module imports a Google Fonts sheet; use local Figtree faces from layout instead.
  webpack(config){config.resolve.alias['@astryxdesign/theme-neutral/fonts.css$']=false;return config},
  async rewrites(){return [{source:'/api/:path*',destination:`${process.env.API_URL||'http://127.0.0.1:8000'}/api/:path*`}]},
});
