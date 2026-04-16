import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  fallback?: ReactNode;
};

type State = {
  hasError: boolean;
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="auth-shell">
          <div className="auth-card" style={{ textAlign: "center" }}>
            <div className="auth-eyebrow">Error</div>
            <h1 className="auth-title" style={{ marginBottom: 12 }}>Something went wrong</h1>
            <p className="auth-copy" style={{ marginBottom: 24 }}>
              An unexpected error occurred. Refreshing the page usually fixes it.
            </p>
            <button
              className="auth-submit"
              onClick={() => window.location.reload()}
            >
              Refresh page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
