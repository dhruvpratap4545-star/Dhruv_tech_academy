import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { inviteWhatsAppUrl } from "@/lib/invites";

export type InviteResult = {
  name: string;
  email: string;
  invitationSent: boolean;
  setupLink: string | null;
};

/**
 * What happened to an invitation, and the two ways to deliver it.
 *
 * Email when it is configured; and always the one-time setup link, to copy or send over
 * WhatsApp — which is how most schools reach people anyway, and the only way at all until
 * email is switched on. The link logs the person straight into password setup, so it is a
 * key: it is shown once, here, to the person who sent the invitation, and nowhere else.
 */
export function InviteLink({
  result,
  onDismiss,
}: {
  result: InviteResult;
  onDismiss?: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!result.setupLink) return;
    try {
      await navigator.clipboard.writeText(result.setupLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be blocked (insecure origin, permissions); the field stays selectable.
    }
  }

  return (
    <Alert
      tone={result.invitationSent ? "success" : "warning"}
      title={`${result.name} has been invited`}
      onDismiss={onDismiss}
    >
      <p>
        {result.invitationSent
          ? `An email with the setup code has been sent to ${result.email}.`
          : `Email is not set up yet, so nothing was emailed to ${result.email}. Share the link below with them instead.`}
      </p>
      {result.setupLink && (
        <div className="mt-3 space-y-2">
          <p className="text-xs">
            You can also share this one-time link. It opens password setup with the code filled in,
            works once, and expires in 48 hours. Send it only to {result.email}.
          </p>
          <input
            readOnly
            value={result.setupLink}
            aria-label="Setup link"
            onFocus={(event) => event.currentTarget.select()}
            className="w-full truncate rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-xs text-fg"
          />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={copy}>
              {copied ? "Copied" : "Copy link"}
            </Button>
            <a
              href={inviteWhatsAppUrl(result.name, result.setupLink)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-8 items-center rounded-md border border-line bg-surface px-3 text-xs font-semibold text-fg hover:bg-surface-2"
            >
              Share on WhatsApp
            </a>
          </div>
        </div>
      )}
    </Alert>
  );
}
