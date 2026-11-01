/** A wa.me link that opens WhatsApp with the invitation text ready to send. */
export function inviteWhatsAppUrl(name: string, setupLink: string): string {
  const text =
    `Hello ${name}, you have been invited to Dhruv Online Academy. ` +
    `Open this link to set your password (it works once and expires in 48 hours): ${setupLink}`;
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}
