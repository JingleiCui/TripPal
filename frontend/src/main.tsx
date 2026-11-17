import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ApiError } from "./api";
import "./style.css";
import "./app-shell.css";
import "../design/tokens.css";
import "./map-first.css";
import "./agent-capabilities.css";
// Tripal 品牌视觉最后引入，覆盖旧品牌样式；统一 Logo 来自 components/TripalLogo。
import "./tripal.css";
import "./travel-workspace.css";
// 每日规划模块视觉精修层最后引入，统一五个视图的排版、间距与动效。
import "./daily-planner.css";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // 4xx 是确定性失败，重试没有意义；网络错误才重试一次。
        if (error instanceof ApiError && error.status >= 400 && error.status < 500)
          return false;
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
    mutations: { retry: false },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
