// Shared password-strength heuristic used by Signup + Reset Password. Purely
// client-side UX guidance; the backend enforces its own minimum length.
export interface PasswordStrength {
  score: 0 | 1 | 2 | 3 | 4;
  label: string;
}

export function passwordStrength(pw: string): PasswordStrength {
  if (!pw) return { score: 0, label: 'Empty' };
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) s++;
  const label = ['Weak', 'Weak', 'Fair', 'Strong', 'Excellent'][s] || 'Weak';
  return { score: s as 0 | 1 | 2 | 3 | 4, label };
}
