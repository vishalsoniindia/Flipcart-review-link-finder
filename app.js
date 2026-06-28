const form = document.querySelector("#review-form");
const productUrlInput = document.querySelector("#product-url");
const reviewerNameInput = document.querySelector("#reviewer-name");
const findButton = document.querySelector("#find-button");
const themeToggle = document.querySelector("#theme-toggle");

const emptyState = document.querySelector("#empty-state");
const reviewState = document.querySelector("#review-state");
const message = document.querySelector("#message");
const confirmBox = document.querySelector("#confirm-box");
const idBox = document.querySelector("#id-box");
const reviewLink = document.querySelector("#review-link");
const copyButton = document.querySelector("#copy-button");
const copyStatus = document.querySelector("#copy-status");

const matchLabel = document.querySelector("#match-label");
const reviewTitle = document.querySelector("#review-title");
const reviewText = document.querySelector("#review-text");
const reviewName = document.querySelector("#review-name");
const reviewDate = document.querySelector("#review-date");
const reviewRating = document.querySelector("#review-rating");
const yesButton = document.querySelector("#yes-button");
const noButton = document.querySelector("#no-button");

let matches = [];
let currentIndex = 0;
let activeTheme = "dark";

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("hidden", !text);
  message.classList.toggle("error", isError);
}

function setCopyStatus(text, isError = false) {
  copyStatus.textContent = text;
  copyStatus.classList.toggle("error", isError);
}

function valueOrDash(value) {
  return value && String(value).trim() ? value : "Not found";
}

function getReviewLink(review) {
  if (!review) return "";
  return `https://www.flipkart.com/reviews/${review.reviewReferenceId}?reviewId=${review.reviewId}`;
}

function setTheme(nextTheme) {
  activeTheme = nextTheme;
  document.body.dataset.theme = nextTheme;
  const darkActive = nextTheme === "dark";
  themeToggle.setAttribute("aria-pressed", String(darkActive));
  themeToggle.textContent = darkActive ? "Dark website" : "Light website";
}

function showReview(index) {
  const review = matches[index];
  if (!review) {
    reviewState.classList.add("hidden");
    emptyState.classList.remove("hidden");
    setMessage("No more reviews found for that name.", true);
    return;
  }

  emptyState.classList.add("hidden");
  reviewState.classList.remove("hidden");
  confirmBox.classList.remove("hidden");
  idBox.classList.add("hidden");

  matchLabel.textContent = `Match ${index + 1} of ${matches.length}`;
  reviewTitle.textContent = valueOrDash(review.title);
  reviewText.textContent = valueOrDash(review.text);
  reviewName.textContent = valueOrDash(review.reviewerName);
  reviewDate.textContent = valueOrDash(review.date);
  reviewRating.textContent = review.rating ? `${review.rating} *` : "*";
  reviewLink.value = getReviewLink(review);
  setCopyStatus("");
  setMessage("");
}

async function findReviews(event) {
  event.preventDefault();
  setMessage("Searching latest Flipkart reviews...");
  findButton.disabled = true;
  findButton.textContent = "Searching...";
  reviewState.classList.add("hidden");
  emptyState.classList.remove("hidden");
  setCopyStatus("");

  try {
    const response = await fetch("/api/find-reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        productUrl: productUrlInput.value,
        reviewerName: reviewerNameInput.value,
      }),
    });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || "Could not search reviews.");
    }

    matches = payload.matches || [];
    currentIndex = 0;

    if (!matches.length) {
      setMessage(
        `No matching review found. Searched ${payload.searchedReviews || 0} reviews.`,
        true
      );
      return;
    }

    showReview(currentIndex);
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    findButton.disabled = false;
    findButton.innerHTML = '<span class="button-icon">Search</span>Find Review';
  }
}

yesButton.addEventListener("click", () => {
  const review = matches[currentIndex];
  if (!review) return;

  confirmBox.classList.add("hidden");
  idBox.classList.remove("hidden");
  reviewLink.value = getReviewLink(review);
  setCopyStatus("");
});

noButton.addEventListener("click", () => {
  currentIndex += 1;
  if (currentIndex >= matches.length) {
    setMessage("No second latest review found for this name.", true);
    return;
  }
  showReview(currentIndex);
});

copyButton.addEventListener("click", async () => {
  const text = reviewLink.value.trim();
  if (!text) return;

  try {
    await navigator.clipboard.writeText(text);
    setCopyStatus("Copied to clipboard.");
  } catch (error) {
    reviewLink.focus();
    reviewLink.select();
    const copied = document.execCommand("copy");
    setCopyStatus(copied ? "Copied to clipboard." : "Copy failed.", !copied);
  }
});

themeToggle.addEventListener("click", () => {
  setTheme(activeTheme === "dark" ? "light" : "dark");
});

form.addEventListener("submit", findReviews);

setTheme("dark");
