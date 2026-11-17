import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, Home, RotateCcw } from "lucide-react";
import { Link } from "react-router-dom";

type Props = {
  children: ReactNode;
  /** 路由变化时重置错误状态，避免一次崩溃后全站不可用。 */
  resetKey?: string;
};

type State = { error: Error | null };

/** 顶层错误边界：任何渲染异常都不应让整个 SPA 变白屏。 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[travel_agent] 渲染异常", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page ui-error-page">
        <div className="ui-state ui-state-error" role="alert">
          <span className="ui-state-icon" aria-hidden="true">
            <AlertTriangle size={24} />
          </span>
          <b>页面遇到了一点问题</b>
          <p>
            当前页面未能正常显示，其他功能不受影响。你可以返回工作台，或重新加载当前页面。
          </p>
          <details className="ui-error-detail">
            <summary>查看技术信息</summary>
            <code>{this.state.error.message}</code>
          </details>
          <div className="ui-state-action">
            <Link to="/" className="btn btn-primary">
              <Home size={15} /> 返回工作台
            </Link>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => this.setState({ error: null })}
            >
              <RotateCcw size={15} /> 重新加载页面
            </button>
          </div>
        </div>
      </div>
    );
  }
}
