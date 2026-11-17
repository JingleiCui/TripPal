import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8808",
      "/_AMapService": "http://127.0.0.1:8808",
      "/s/": "http://127.0.0.1:8808",
    },
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // 把稳定的第三方依赖拆成可长期缓存的块，而不是抬高告警阈值掩盖问题。
        manualChunks(id) {
          const path = id.replace(/\\/g, "/");
          if (!path.includes("/node_modules/")) return;
          if (
            path.includes("/node_modules/react/") ||
            path.includes("/node_modules/react-dom/") ||
            path.includes("/node_modules/scheduler/")
          )
            return "vendor-react";
          if (path.includes("/node_modules/react-router")) return "vendor-router";
          if (path.includes("/node_modules/@tanstack")) return "vendor-query";
          if (path.includes("/node_modules/lucide-react")) return "vendor-icons";
          if (
            /react-markdown|remark-|rehype-|micromark|mdast|hast|unist|unified|vfile/.test(
              path,
            )
          )
            return "vendor-markdown";
          return "vendor";
        },
      },
    },
  },
});
