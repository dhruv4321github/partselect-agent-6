const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function (app) {
  app.use(
    "/api",
    createProxyMiddleware({
      target: "http://localhost:8000",
      changeOrigin: true,
      onProxyRes(proxyRes) {
        // Disable buffering so SSE events stream through in real time.
        proxyRes.headers["X-Accel-Buffering"] = "no";
        proxyRes.headers["Cache-Control"] = "no-cache";
      },
    })
  );
};
