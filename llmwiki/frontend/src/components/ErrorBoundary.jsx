import React from "react";

/**
 * ErrorBoundary — 捕获子组件渲染错误,防止单个视图崩溃导致整个 App 白屏。
 * 用法: <ErrorBoundary fallback={<div>出错了</div>}><MyView /></ErrorBoundary>
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[ErrorBoundary]", this.props.name || "unknown", error, errorInfo);
  }

  componentDidUpdate(prevProps) {
    // 当 props.key 变化时重置(允许用户切走再切回时自动恢复)
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, error: null });
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return typeof this.props.fallback === "function"
          ? this.props.fallback(this.state.error)
          : this.props.fallback;
      }
      return (
        <div className="card" style={{ padding: 40, textAlign: "center" }}>
          <div style={{ fontSize: 28, marginBottom: 12 }}>⚠️</div>
          <div className="card-title" style={{ marginBottom: 6 }}>该模块出了点问题</div>
          <div className="muted" style={{ marginBottom: 16, maxWidth: 400, margin: "0 auto 16px" }}>
            {this.state.error?.message || "未知错误"}
          </div>
          <button className="btn primary" onClick={() => this.setState({ hasError: false, error: null })}>
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
