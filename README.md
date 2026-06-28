# Flipkart Review Finder

A local GUI website for finding the newest Flipkart review by reviewer name, confirming whether it is yours, and showing `reviewReferenceId` plus `reviewId`.

## Run

```powershell
python server.py
```

Open:

```text
http://127.0.0.1:8000
```

The app uses a local Python proxy because browsers cannot reliably fetch Flipkart pages directly. Flipkart may still block automated requests; when that happens, the app shows the server error in the UI.

## Flipkart review fields

On the current Flipkart review page, each review is inside `window.__INITIAL_STATE__` as a `ProductReviewValue`.

- `reviewId` is the review object's `id`.
- `reviewReferenceId` is extracted from the review object's `url`, which looks like `/reviews/<reviewReferenceId>?reviewId=<reviewId>`.
