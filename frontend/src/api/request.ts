export async function expectData<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request;
  if (error) {
    const detail =
      typeof error === "object" && error !== null
        ? JSON.stringify(error)
        : String(error);
    throw new Error(`API ${response.status}: ${detail}`);
  }
  if (data === undefined) {
    throw new Error(`API ${response.status}: empty response`);
  }
  return data;
}
