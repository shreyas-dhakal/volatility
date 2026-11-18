const withStyleX = require('@stylexswc/nextjs-plugin');
module.exports = withStyleX({rsOptions:{exclude:['**/node_modules/**']}})({
  poweredByHeader:false,
  devIndicators:false,
  async rewrites(){return [{source:'/api/:path*',destination:`${process.env.API_URL||'http://127.0.0.1:8000'}/api/:path*`}]},
});
