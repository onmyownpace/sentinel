"use client";

import { useState, type FormEvent } from "react";

import {
  createWebsite,
  validateWebsiteInput,
  WebsiteApiError,
  type FieldErrors,
  type Website,
} from "@/lib/websites";

type WebsiteFormProps = {
  onCreated: (website: Website) => void;
};

export function WebsiteForm({ onCreated }: WebsiteFormProps) {
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validateWebsiteInput({ name, base_url: baseUrl });
    if (nextErrors.name || nextErrors.baseUrl) {
      setErrors(nextErrors);
      return;
    }

    setSubmitting(true);
    setErrors({});
    try {
      const website = await createWebsite({ name, base_url: baseUrl });
      setName("");
      setBaseUrl("");
      onCreated(website);
    } catch (error) {
      if (error instanceof WebsiteApiError) {
        setErrors(
          error.fieldErrors.form || error.fieldErrors.name || error.fieldErrors.baseUrl
            ? error.fieldErrors
            : { form: error.message },
        );
      } else {
        setErrors({ form: "The website could not be saved." });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card stack" onSubmit={onSubmit} noValidate>
      <h2>Add a website</h2>
      {errors.form ? (
        <p className="banner bad" role="alert">
          {errors.form}
        </p>
      ) : null}
      <label htmlFor="website-name">
        Name
        <input
          id="website-name"
          name="name"
          type="text"
          value={name}
          maxLength={120}
          disabled={submitting}
          aria-invalid={errors.name ? true : undefined}
          aria-describedby={errors.name ? "website-name-error" : undefined}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      {errors.name ? (
        <p id="website-name-error" className="field-error" role="alert">
          {errors.name}
        </p>
      ) : null}
      <label htmlFor="website-url">
        Base URL
        <input
          id="website-url"
          name="base_url"
          type="text"
          inputMode="url"
          spellCheck={false}
          placeholder="https://example.com"
          value={baseUrl}
          disabled={submitting}
          aria-invalid={errors.baseUrl ? true : undefined}
          aria-describedby={errors.baseUrl ? "website-url-hint website-url-error" : "website-url-hint"}
          onChange={(event) => setBaseUrl(event.target.value)}
        />
      </label>
      <p id="website-url-hint" className="hint tight">
        HTTP and HTTPS only. A trailing slash is stored as the same URL.
      </p>
      {errors.baseUrl ? (
        <p id="website-url-error" className="field-error" role="alert">
          {errors.baseUrl}
        </p>
      ) : null}
      <div className="actions">
        <button className="primary" type="submit" disabled={submitting}>
          {submitting ? "Adding…" : "Add website"}
        </button>
      </div>
    </form>
  );
}
