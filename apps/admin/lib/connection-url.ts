export type ParsedConnection = {
  connection: string;
  username: string;
  database: string;
};

export function parseConnectionUrl(url: string): ParsedConnection | null {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname || "localhost";
    const port = parsed.port ? Number(parsed.port) : 3306;
    const username = decodeURIComponent(parsed.username || "root");
    const database = decodeURIComponent((parsed.pathname || "/").replace(/^\//, ""));

    return {
      connection: `${host}:${port}`,
      username,
      database: database || "-",
    };
  } catch {
    return null;
  }
}
