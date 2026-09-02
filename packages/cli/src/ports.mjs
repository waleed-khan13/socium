import net from "node:net";

function validPort(port) {
  return Number.isInteger(port) && port >= 1 && port <= 65_535;
}

export async function isPortAvailable(port, host = "127.0.0.1") {
  if (!validPort(port)) return false;
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen({ host, port }, () => server.close(() => resolve(true)));
  });
}

export async function findAvailablePort(
  preferredPort,
  { exclude = [], host = "127.0.0.1", maxSequentialAttempts = 100 } = {},
) {
  if (!validPort(preferredPort)) {
    throw new Error("Preferred port must be between 1 and 65535.");
  }
  const excluded = new Set(exclude.filter(validPort));
  for (let offset = 0; offset <= maxSequentialAttempts; offset += 1) {
    const candidate = preferredPort + offset;
    if (candidate > 65_535) break;
    if (!excluded.has(candidate) && await isPortAvailable(candidate, host)) return candidate;
  }

  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen({ host, port: 0 }, () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => {
        if (!validPort(port) || excluded.has(port)) {
          reject(new Error("Could not find a free local port for Socium."));
          return;
        }
        resolve(port);
      });
    });
  });
}
