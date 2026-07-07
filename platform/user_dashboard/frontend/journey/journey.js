import { el, showModalContent } from "../dom.js";

export function renderJourney(payload, state = {}, actions = {}) {
  const chapters = payload.journey?.chapters || [
    { title: "Luke 1", status: "continue" },
    { title: "Luke 2", status: "continue" }
  ];
  const summary = payload.journey?.summary || {};
  const target = activeJourneyTarget(chapters);
  const activeChapter = target.chapter;
  const activeChapterIndex = Number.isInteger(summary.active_chapter_index)
    ? summary.active_chapter_index
    : target.chapterIndex;
  const completedBatchCount = Number.isFinite(Number(summary.batches_done))
    ? Number(summary.batches_done)
    : completedBatches(chapters, payload);
  const batchProgress = Number.isFinite(Number(summary.overall_progress))
    ? Number(summary.overall_progress)
    : overallBatchProgress(chapters);

  const selectedChapter = Number.isInteger(state.journeyChapterIndex)
    ? chapters[state.journeyChapterIndex]
    : null;
  const answerTarget = state.journeyAnswerQuestion
    ? compactAnswerTarget(state.journeyAnswerQuestion, chapters)
    : state.journeyAnswerAssignmentId
      ? findQuestionByAssignment(chapters, state.journeyAnswerAssignmentId)
      : null;
  const completion = state.questionCompletion || null;
  const body = completion
    ? renderQuestionCompletedPage(completion, actions)
    : answerTarget
    ? renderQuestionAnswerPage(answerTarget, actions)
    : selectedChapter
    ? renderChapterPath(selectedChapter, state.journeyChapterIndex, actions)
    : renderStandaloneContinue(activeChapterIndex, actions);
  const header = selectedChapter || answerTarget || completion ? [] : [
    el("section", { className: "journey-hero" }, [
      el("div", {}, [
        el("p", { className: "journey-kicker", text: "Current path" }),
        el("h1", { text: summary.current_path || batchLabel(target.batch, target.batchIndex) }),
        el("p", {
          className: "journey-copy",
          text: "Keep moving through the path and complete each question batch."
        })
      ]),
      el("div", { className: "journey-progress-ring", style: `--progress:${Math.round(batchProgress * 100)}%` }, [
        el("strong", { text: `${Math.round(batchProgress * 100)}%` }),
        el("span", { text: "overall" })
      ])
    ]),
    el("div", { className: "journey-stats" }, [
      stat("Batches done", String(completedBatchCount)),
      stat("Current chapter", summary.current_chapter || chapterLabel(activeChapter, activeChapterIndex)),
      stat("Next reward", summary.next_reward || "Daily streak")
    ])
  ];

  return el("section", { className: "journey-page" }, [
    ...header,
    body
  ]);
}

function renderStandaloneContinue(index, actions) {
  return el("section", { className: "journey-continue-panel" }, [
    el("button", {
      type: "button",
      className: "journey-continue-btn",
      onclick: () => actions.setJourneyChapter?.(index),
      text: "Continue"
    })
  ]);
}

function renderQuestionCompletedPage(completion, actions) {
  const submission = completion.submission || {};
  const awards = completion.awards || {};
  const pending = completion.pending === true;
  const failed = completion.failed === true;
  const batchCompleted = submission.batch_completed === true;
  const answerAward = Math.max(0, Number(awards.answer || 0));
  const batchAward = Math.max(0, Number(awards.batch_completed || 0));
  const headline = failed
    ? "Could not save"
    : pending
      ? "Question complete!"
      : completionHeadline(submission.is_correct, batchCompleted);
  const subline = failed
    ? completion.errorMessage || "Please go back and try again."
    : pending
      ? "Saving your answer..."
      : batchCompleted
    ? "Batch finished. Your path is updated."
    : "Nice work. The next question is ready.";
  const buttonText = failed ? "Back" : batchCompleted ? "Back to map" : "Continue";

  return el("section", { className: "question-complete-page" }, [
    el("div", { className: "complete-burst", "aria-hidden": "true" }),
    el("div", { className: "complete-confetti", "aria-hidden": "true" }, confettiPieces()),
    el("div", { className: "complete-check-wrap" }, [
      el("div", { className: "complete-check-ring" }, [
        el("img", {
          className: "complete-check-icon",
          src: "/user_dashboard/assets/checkmark.svg",
          alt: "",
          "aria-hidden": "true"
        })
      ]),
      el("span", { className: "complete-star star-one", text: "*" }),
      el("span", { className: "complete-star star-two", text: "*" }),
      el("span", { className: "complete-star star-three", text: "*" }),
      el("span", { className: "complete-star star-four", text: "*" })
    ]),
    el("h1", { className: "complete-headline", text: headline }),
    el("p", { className: "complete-sub", text: subline }),
    !pending && !failed ? el("div", { className: "complete-reward-row" }, [
      el("div", { className: "complete-reward-pill" }, [
        el("img", {
          src: "/user_dashboard/assets/diamond.svg",
          alt: "",
          "aria-hidden": "true"
        }),
        el("div", {}, [
          el("strong", { text: `+${answerAward}` }),
          el("span", { text: "diamonds" })
        ])
      ]),
      batchAward > 0 ? el("div", { className: "complete-reward-pill bonus" }, [
        el("span", { className: "complete-reward-symbol", text: "+" }),
        el("div", {}, [
          el("strong", { text: `+${batchAward}` }),
          el("span", { text: "batch bonus" })
        ])
      ]) : null
    ]) : null,
    batchCompleted ? el("div", { className: "complete-batch-box" }, [
      el("strong", { text: "Batch complete" }),
      el("span", { text: "Open the chest on the map or start another batch when it is available." })
    ]) : null,
    el("button", {
      type: "button",
      className: `complete-cta ${pending ? "pending" : ""} ${failed ? "failed" : ""}`,
      disabled: pending ? true : null,
      onclick: () => actions.continueAfterAnswer?.(),
    }, [
      pending ? el("span", { className: "button-spinner", "aria-hidden": "true" }) : null,
      el("span", { text: pending ? "Preparing next question..." : buttonText })
    ])
  ]);
}

function completionHeadline(isCorrect, batchCompleted) {
  if (String(isCorrect || "").toLowerCase().startsWith("yes")) {
    return batchCompleted ? "Correct! Batch complete!" : "Correct!";
  }
  if (String(isCorrect || "").toLowerCase().startsWith("no")) {
    return batchCompleted ? "Question complete!" : "Answer submitted";
  }
  return batchCompleted ? "Batch complete!" : "Question complete!";
}

function confettiPieces() {
  const colors = ["#58cc02", "#ffd060", "#ff4b4b", "#48c8ff", "#ff9600"];
  return Array.from({ length: 34 }, (_, index) => {
    const left = 8 + ((index * 23) % 86);
    const size = 7 + (index % 4) * 2;
    const duration = 1.8 + (index % 5) * 0.22;
    const delay = (index % 7) * 0.08;
    return el("span", {
      className: "complete-confetti-piece",
      style: [
        `left:${left}%`,
        `width:${size}px`,
        `height:${size}px`,
        `background:${colors[index % colors.length]}`,
        `animation-duration:${duration}s`,
        `animation-delay:${delay}s`,
        `border-radius:${index % 3 === 0 ? "50%" : "3px"}`
      ].join(";")
    });
  });
}

function renderQuestionAnswerPage(target, actions) {
  const { chapter, batch, question, questionIndex } = target;
  const questionType = String(question.question_type || "open").toLowerCase();
  const choices = Array.isArray(question.mcq_choices) ? question.mcq_choices : [];
  const isChoice = questionType === "mcq" || questionType === "tf";
  const answerName = `answer-${question.assignment_id}`;

  return el("section", { className: "question-answer-page" }, [
    el("div", { className: "question-answer-toolbar" }, [
      el("button", {
        type: "button",
        className: "chapter-back-btn",
        onclick: () => actions.closeQuestion?.(),
        text: "Back"
      }),
      el("div", {}, [
        el("span", {
          className: "journey-kicker",
          text: `${chapter?.title || "Question path"} / ${batch?.label || "Batch"}`
        }),
        el("h2", { text: `Question ${questionIndex + 1}` })
      ])
    ]),
    el("form", {
      className: "question-answer-card",
      onsubmit: (event) => {
        event.preventDefault();
        const formData = new FormData(event.currentTarget);
        const responseText = String(formData.get("response_text") || "").trim();
        actions.submitAnswer?.(question.assignment_id, responseText);
      }
    }, [
      question.passage_reference
        ? el("div", { className: "answer-reference", text: question.passage_reference })
        : null,
      el("h1", { text: question.question || "Question" }),
      question.audio_url
        ? el("audio", { className: "answer-audio", controls: true, src: question.audio_url })
        : null,
      isChoice
        ? renderChoiceAnswer(answerName, choices, questionType)
        : renderOpenAnswer(),
      el("div", { className: "answer-actions" }, [
        el("button", {
          type: "submit",
          className: "answer-submit-btn",
          text: "Submit answer"
        })
      ])
    ])
  ]);
}

function renderChoiceAnswer(answerName, choices, questionType) {
  const letters = questionType === "tf" ? ["A", "B"] : ["A", "B", "C", "D"];
  return el("div", { className: "choice-answer-list" }, choices.map((choice, index) => {
    const letter = letters[index] || String(index + 1);
    const id = `${answerName}-${letter}`;
    return el("label", { className: "choice-answer-option", for: id }, [
      el("input", {
        id,
        type: "radio",
        name: "response_text",
        value: letter,
        required: true
      }),
      el("span", { className: "choice-letter", text: letter }),
      el("span", { className: "choice-text", text: choice })
    ]);
  }));
}

function renderOpenAnswer() {
  return el("label", { className: "open-answer-field" }, [
    el("span", { text: "Your answer" }),
    el("textarea", {
      name: "response_text",
      rows: "5",
      required: true,
      placeholder: "Type your answer here..."
    })
  ]);
}

function renderChapterPath(chapter, index, actions) {
  const batches = pathBatches(chapter);
  const currentBatch = batches.find((batch) => batch.status === "active")
    || batches.find((batch) => batch.status !== "complete")
    || batches[batches.length - 1]
    || null;
  scheduleCurrentQuestionJump();
  return el("section", { className: "chapter-path-page" }, [
    el("div", { className: "chapter-path-toolbar" }, [
      el("button", {
        type: "button",
        className: "chapter-back-btn",
        onclick: () => actions.clearJourneyChapter?.(),
        text: "Back"
      }),
      el("div", {}, [
        el("span", { className: "journey-kicker", text: chapter.title || "Question path" }),
        el("h2", { text: "Batch path" })
      ]),
      currentBatch ? el("button", {
        type: "button",
        className: "active-batch-pill",
        onclick: () => jumpToBatch(currentBatch.batch_id),
        text: currentBatch.label || "Current batch"
      })
        : null
    ]),
    el("div", { className: "chapter-path-scroll" }, batches.map((batch, batchIndex) => (
      renderBatchPath(batch, batchIndex, actions, batchIndex === batches.length - 1)
    )))
  ]);
}

function pathBatches(chapter) {
  const batches = Array.isArray(chapter.batches) ? chapter.batches : fallbackBatches(chapter);
  const currentIndex = Math.max(0, Number(chapter.current_batch_index || 0));
  const activeIndex = batches.findIndex((batch) => batch.status !== "complete");
  const endIndex = activeIndex >= 0 ? activeIndex : currentIndex;
  return batches.slice(0, Math.min(batches.length, endIndex + 1));
}

function activeJourneyTarget(chapters) {
  for (const [chapterIndex, chapter] of chapters.entries()) {
    const batches = chapterBatches(chapter);
    if (!batches.length && chapter.status !== "complete") {
      return {
        chapter,
        chapterIndex,
        batch: null,
        batchIndex: 0
      };
    }
    const batchIndex = batches.findIndex((batch) => batch.status !== "complete");
    if (batchIndex >= 0) {
      return {
        chapter,
        chapterIndex,
        batch: batches[batchIndex],
        batchIndex
      };
    }
  }
  const fallbackChapter = chapters[chapters.length - 1] || {};
  const fallbackBatches = chapterBatches(fallbackChapter);
  return {
    chapter: fallbackChapter,
    chapterIndex: Math.max(0, chapters.length - 1),
    batch: fallbackBatches[fallbackBatches.length - 1] || null,
    batchIndex: Math.max(0, fallbackBatches.length - 1)
  };
}

function chapterBatches(chapter) {
  return Array.isArray(chapter?.batches) ? chapter.batches : [];
}

function completedBatches(chapters, payload) {
  const batches = chapters.flatMap(chapterBatches);
  if (!batches.length) {
    return Number(payload.history_summary?.total_batches_answered || 0);
  }
  return batches.filter((batch) => batch.status === "complete").length;
}

function overallBatchProgress(chapters) {
  const batches = chapters.flatMap(chapterBatches);
  if (!batches.length) {
    return chapters.length
      ? chapters.reduce((sum, chapter) => sum + normalizedProgress(chapter), 0) / chapters.length
      : 0;
  }
  const completedQuestions = batches.reduce((sum, batch) => (
    sum + batchQuestions(batch).filter((question) => question.status === "complete").length
  ), 0);
  const totalQuestions = batches.reduce((sum, batch) => sum + batchQuestions(batch).length, 0);
  return totalQuestions ? completedQuestions / totalQuestions : 0;
}

function batchQuestions(batch) {
  return Array.isArray(batch?.questions) ? batch.questions : [];
}

function batchLabel(batch, index) {
  return batch?.label || `Batch ${index + 1}`;
}

function chapterLabel(chapter, index) {
  if (Number(chapter?.chapter)) {
    return `Chapter ${Number(chapter.chapter)}`;
  }
  const match = String(chapter?.title || "").match(/\d+/);
  return match ? `Chapter ${match[0]}` : `Chapter ${index + 1}`;
}

function fallbackBatches(chapter) {
  const progress = normalizedProgress(chapter);
  const completed = Math.round(progress * 3);
  const questions = Array.from({ length: 3 }, (_, index) => ({
    status: index < completed ? "complete" : index === completed ? "current" : "locked",
    question: `Question ${index + 1}`
  }));
  return [
    {
      label: "Batch 1",
      status: progress >= 1 ? "complete" : "active",
      questions
    },
    {
      label: "Batch 2",
      status: "locked",
      questions: [{ status: "locked", question: "Next batch" }]
    }
  ];
}

function renderBatchPath(batch, batchIndex, actions, isLastBatch = false) {
  const questions = Array.isArray(batch.questions) && batch.questions.length
    ? batch.questions
    : [{ status: batch.status || "locked", question: "Question" }];
  const positions = batchNodePositions(questions.length);
  const rewardPosition = rewardNodePosition(positions);
  const showStartBatch = isLastBatch && batch.status === "complete";
  const mapHeight = rewardPosition.top + (showStartBatch ? 188 : 126);
  return el("section", {
    className: `batch-path-section ${batch.status || ""}`,
    "data-batch-id": batch.batch_id || batch.label || `batch-${batchIndex + 1}`
  }, [
    el("div", { className: "batch-label" }, [
      el("div", { className: "batch-line" }),
      el("div", { className: "batch-text", text: batch.label || "Batch" }),
      el("div", { className: "batch-line" })
    ]),
    el("div", { className: "path-map", style: `height:${mapHeight}px` }, [
      ...questions.map((question, index) => renderPathNode(question, index, positions[index], batchIndex, actions)),
      renderRewardNode(batch, rewardPosition, actions),
      showStartBatch ? renderStartNewBatchButton(rewardPosition, actions) : null
    ])
  ]);
}

function renderStartNewBatchButton(position, actions) {
  return el("div", {
    className: "start-batch-node-wrap",
    style: `top:${position.top + 108}px`
  }, [
    el("button", {
      type: "button",
      className: `start-batch-map-btn ${actions.startingBatch ? "loading" : ""}`,
      disabled: actions.startingBatch ? true : null,
      onclick: () => actions.startNewBatch?.(),
    }, [
      actions.startingBatch ? el("span", { className: "button-spinner", "aria-hidden": "true" }) : null,
      el("span", { text: actions.startingBatch ? "Starting..." : "Start new batch" })
    ])
  ]);
}

function findQuestionByAssignment(chapters, assignmentId) {
  for (const [chapterIndex, chapter] of chapters.entries()) {
    for (const [batchIndex, batch] of chapterBatches(chapter).entries()) {
      for (const [questionIndex, question] of batchQuestions(batch).entries()) {
        if (question.assignment_id === assignmentId) {
          return { chapter, chapterIndex, batch, batchIndex, question, questionIndex };
        }
      }
    }
  }
  return null;
}

function compactAnswerTarget(question, chapters) {
  const fallback = activeJourneyTarget(chapters);
  return {
    chapter: {
      title: question.chapter_label || fallback.chapter?.title || "Question path"
    },
    chapterIndex: fallback.chapterIndex || 0,
    batch: {
      label: fallback.batch?.label || "Current batch",
      batch_id: question.batch_id
    },
    batchIndex: fallback.batchIndex || 0,
    question,
    questionIndex: Number.isFinite(Number(question.question_index))
      ? Number(question.question_index)
      : 0
  };
}

function renderPathNode(question, index, position, batchIndex, actions = {}) {
  const status = question.status || "locked";
  const isCurrent = status === "current";
  return el("div", {
    className: `path-node-wrap node-${status}`,
    style: `top:${position.top}px;left:${position.left}px`,
    "data-current-question": isCurrent ? "true" : null
  }, [
    el("button", {
      type: "button",
      className: `path-node ${status}`,
      title: question.question || `Question ${index + 1}`,
      onclick: status === "complete"
        ? () => showCompletedQuestion(question)
        : isCurrent
          ? () => actions.openQuestion?.(question.assignment_id)
          : null,
      "aria-label": `${batchIndex + 1}.${index + 1} ${question.question || "Question"}`
    }, [
      status === "complete"
        ? el("img", { src: "/user_dashboard/assets/checkmark.svg", alt: "", "aria-hidden": "true" })
        : status === "locked"
          ? el("img", { className: "lock-icon", src: "/user_dashboard/assets/lock.svg", alt: "", "aria-hidden": "true" })
          : el("span", { text: isCurrent ? `${index + 1}` : "" })
    ]),
    isCurrent ? el("span", { className: "node-tooltip", text: "Continue" }) : null
  ]);
}

function renderRewardNode(batch, position, actions = {}) {
  const reward = batch.reward || {};
  const opened = reward.claimed === true;
  const claimable = reward.claimable === true;
  const loading = actions.claimingBatchRewardId === batch.batch_id;
  const unopened = !opened;
  const rewardText = `The box has ${reward.min || 2}-${reward.max || 5} diamonds`;
  const chestNode = el(claimable ? "button" : "div", {
    type: claimable ? "button" : null,
    className: `path-node chest ${opened ? "unlocked" : ""} ${unopened ? "next-reward" : ""} ${claimable ? "claimable" : ""} ${loading ? "loading" : ""}`,
    disabled: loading ? true : null,
    "aria-label": opened
      ? `Opened batch reward${reward.amount ? `, ${reward.amount} diamonds` : ""}`
      : loading
        ? "Opening chest"
        : rewardText,
    title: opened
      ? `Opened${reward.amount ? `: ${reward.amount} diamonds` : ""}`
      : loading
        ? "Opening chest..."
        : rewardText,
    onclick: claimable && !loading ? () => actions.claimBatchReward?.(batch.batch_id) : null
  }, [
    el("img", {
      className: "chest-icon",
      src: opened ? "/user_dashboard/assets/chest_opened.svg" : "/user_dashboard/assets/chest_unopened.svg",
      alt: "",
      "aria-hidden": "true"
    }),
    loading ? el("span", { className: "chest-loading-overlay" }, [
      el("span", { className: "button-spinner", "aria-hidden": "true" })
    ]) : null
  ]);

  return el("div", {
    className: `path-node-wrap reward-node-wrap ${unopened ? "has-chest-preview" : ""}`,
    style: `top:${position.top}px;left:${position.left}px`
  }, [
    chestNode,
    unopened ? chestRewardPreview(rewardText, claimable) : null
  ]);
}

function chestRewardPreview(rewardText, claimable) {
  return el("div", { className: "chest-reward-preview", role: "tooltip" }, [
    el("span", { className: "chest-preview-sparkle", text: "*" }),
    el("span", { className: "chest-preview-sparkle", text: "*" }),
    el("div", { className: "chest-preview-eyebrow", text: "Treasure chest" }),
    el("div", { className: "chest-preview-title", text: rewardText }),
    claimable ? el("div", { className: "chest-preview-arrow", text: "↓" }) : null
  ]);
}

function batchNodePositions(total) {
  const count = Math.max(1, total);
  const turnIndex = Math.ceil(count / 2);
  const left = 150;
  const right = 390;
  const top = 8;
  const rowGap = 122;
  const firstRow = Array.from({ length: turnIndex }, (_, index) => ({
    top: top + index * rowGap,
    left: interpolate(left, right, turnIndex, index)
  }));
  const secondCount = count - turnIndex;
  const secondRow = Array.from({ length: secondCount }, (_, index) => ({
    top: top + (turnIndex + index) * rowGap + (index === 0 && secondCount > 1 ? 24 : 0),
    left: interpolate(right, left, secondCount + 1, index + 1) + (index === 0 && secondCount > 1 ? 28 : 0)
  }));
  return [...firstRow, ...secondRow];
}

function rewardNodePosition(positions) {
  const last = positions[positions.length - 1] || { top: 32, left: 26 };
  const previous = positions[positions.length - 2];
  const movingLeft = previous ? last.left < previous.left : false;
  return {
    top: last.top + 110,
    left: movingLeft ? Math.max(12, last.left - 130) : Math.min(480, last.left + 130)
  };
}

function interpolate(start, end, count, index) {
  if (count <= 1) {
    return Math.round((start + end) / 2);
  }
  return Math.round(start + ((end - start) * index) / (count - 1));
}

function scheduleCurrentQuestionJump() {
  window.requestAnimationFrame?.(() => {
    window.requestAnimationFrame?.(() => {
      const current = document.querySelector('[data-current-question="true"]');
      current?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    });
  });
}

function jumpToBatch(batchId) {
  if (!batchId) {
    return;
  }
  const selector = `[data-batch-id="${cssEscape(batchId)}"]`;
  const batch = document.querySelector(selector);
  batch?.scrollIntoView({ behavior: "smooth", block: "start", inline: "center" });
}

function cssEscape(value) {
  if (window.CSS?.escape) {
    return window.CSS.escape(value);
  }
  return String(value).replace(/["\\]/g, "\\$&");
}

function showCompletedQuestion(question) {
  const review = question.review || {};
  showModalContent("Completed question", [
    detailBlock("Question", [
      el("p", { text: review.question || question.question || "Question" })
    ]),
    detailBlock("Your answer", [
      el("p", { text: review.participant_answer || "No answer recorded" }),
      review.participant_audio_url
        ? el("audio", { controls: true, src: review.participant_audio_url })
        : null
    ]),
    detailBlock("Correct answer", [
      el("p", { text: review.correct_answer || "No answer recorded" }),
      review.correct_audio_url
        ? el("audio", { controls: true, src: review.correct_audio_url })
        : null
    ]),
    review.correctness
      ? el("p", { className: "question-review-status", text: `Status: ${review.correctness}` })
      : null
  ]);
}

function detailBlock(label, children) {
  return el("section", { className: "question-review-block" }, [
    el("h3", { text: label }),
    ...children
  ]);
}

function stat(label, value) {
  return el("article", { className: "journey-stat" }, [
    el("span", { text: label }),
    el("strong", { text: value })
  ]);
}

function normalizedProgress(chapter) {
  if (chapter.status === "complete") {
    return 1;
  }
  return Math.max(0, Math.min(1, Number(chapter.progress || 0)));
}
