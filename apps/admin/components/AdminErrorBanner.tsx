"use client";

export function AdminErrorBanner({
  message,
  onDismiss,
}: {
  message: string | null;
  onDismiss?: () => void;
}) {
  if (!message) return null;
  return (
    <div
      className="admin-error-banner"
      role="alert"
      style={{
        background: "#7f1d1d",
        color: "#fecaca",
        padding: "0.75rem 1rem",
        borderRadius: "6px",
        marginBottom: "1rem",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        gap: "1rem",
      }}
    >
      <span style={{ whiteSpace: "pre-wrap", fontSize: "0.875rem" }}>{message}</span>
      {onDismiss && (
        <button
          type="button"
          className="btn btn-sm"
          onClick={onDismiss}
          style={{ flexShrink: 0 }}
        >
          关闭
        </button>
      )}
    </div>
  );
}
