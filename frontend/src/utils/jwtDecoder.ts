/**
 * JWT Token Utilities
 * Provides functions for decoding JWT tokens and extracting user information.
 */

interface JwtPayload extends Record<string, unknown> {
  sub: string;
  email?: string;
  email_verified?: boolean;
  iat?: number;
  exp?: number;
}

const isJwtPayload = (value: unknown): value is JwtPayload => {
  return typeof value === 'object'
    && value !== null
    && typeof (value as Record<string, unknown>).sub === 'string';
};

export const decodeJwt = (token: string): JwtPayload => {
  try {
    const parts = token.split('.');

    if (parts.length !== 3) {
      throw new Error('Invalid JWT token format');
    }

    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const paddedBase64 = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const jsonPayload = decodeURIComponent(
      atob(paddedBase64)
        .split('')
        .map((character) => `%${character.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join(''),
    );
    const payload: unknown = JSON.parse(jsonPayload);

    if (!isJwtPayload(payload)) {
      throw new Error('JWT payload does not contain a valid sub claim');
    }

    return payload;
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    throw new Error(`Failed to decode JWT token: ${message}`);
  }
};

export const extractUserId = (token: string): string => decodeJwt(token).sub;
