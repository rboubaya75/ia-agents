/**
 * JWT Token Utilities
 * Provides functions for decoding JWT tokens and extracting user information
 */

/**
 * Decoded JWT payload interface
 */
interface JwtPayload {
  sub: string; // Cognito User ID
  email?: string;
  email_verified?: boolean;
  iat?: number;
  exp?: number;
  [key: string]: any;
}

/**
 * Decodes a JWT token and returns the payload
 * @param token - The JWT token string
 * @returns The decoded JWT payload
 * @throws Error if the token is invalid or cannot be decoded
 */
export const decodeJwt = (token: string): JwtPayload => {
  try {
    // JWT structure: header.payload.signature
    const parts = token.split('.');
    
    if (parts.length !== 3) {
      throw new Error('Invalid JWT token format');
    }

    // Extract the payload (second part)
    const base64Url = parts[1];
    
    // Convert base64url to base64
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    
    // Decode base64 to JSON string
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    
    return JSON.parse(jsonPayload) as JwtPayload;
  } catch (error) {
    throw new Error(`Failed to decode JWT token: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
};

/**
 * Extracts the User ID from a Cognito JWT token
 * @param token - The JWT token string
 * @returns The user ID (sub claim) from the token
 * @throws Error if the token is invalid or doesn't contain a sub claim
 */
export const extractUserId = (token: string): string => {
  const decoded = decodeJwt(token);
  
  if (!decoded.sub) {
    throw new Error('JWT token does not contain a sub claim');
  }
  
  return decoded.sub;
};
