"""Deterministic action-verb detection.

The content score used to rely on the list of action verbs returned by the LLM
parser, which changes a little from run to run. Counting the verbs that start
bullet points and sentences in the resume text gives the same answer every
time for the same resume.
"""

import re
from typing import List

# Past-tense forms are the resume convention; a few unambiguous present-tense
# forms are included for current roles. Words that are also common job-title
# nouns (design, lead, research, support, test, ...) are left out on purpose.
ACTION_VERBS = frozenset("""
accelerated achieved acquired adapted addressed administered advised aligned analyzed analysed
architected assembled assessed assisted audited authored automated balanced benchmarked boosted
briefed budgeted built calculated captured championed clarified coached collaborated collected
communicated compiled completed composed conceived conducted configured consolidated constructed
consulted containerized contributed controlled converted coordinated created crafted customized
debugged decreased defined delivered demonstrated deployed designed detected determined developed
devised diagnosed directed discovered documented doubled drafted drove earned edited eliminated
enabled enforced engineered enhanced ensured established estimated evaluated examined executed
expanded expedited explored extended extracted fabricated facilitated finalized fixed forecasted
formulated founded generated guided handled headed identified implemented improved incorporated
increased influenced initiated innovated inspected installed instituted integrated interpreted
introduced invented investigated launched led leveraged maintained managed mapped maximized
measured mentored merged migrated minimized modeled modelled modernized monitored motivated
negotiated normalized operated optimized orchestrated organized outperformed overhauled oversaw
owned partnered performed pioneered planned prepared presented prioritized processed produced
programmed prototyped provided published purchased queried raised ran rebuilt received
recommended reconciled recorded recruited redesigned reduced refactored refined released replaced
reported researched resolved restructured retrieved revamped reviewed revised scaled scheduled
scripted secured selected served shaped shipped simplified simulated solved sourced spearheaded
standardized streamlined strengthened structured supervised supported surpassed synthesized
tailored tested tracked trained transformed translated troubleshot tuned uncovered unified
updated upgraded utilized validated verified visualized won wrote
analyze automate collaborate conduct configure contribute coordinate create deliver deploy develop
enhance establish evaluate execute implement improve integrate maintain manage migrate optimize
organize perform provide reduce refactor resolve streamline troubleshoot write
""".split())

_BULLET_GLYPHS = re.compile("[\u2022\u25cf\u25aa\u25e6\u2023\u00b7\uf0b7\uf0a7]")
_LEADING_JUNK = re.compile(r"^(?:[\s\-\*>\u2013\u2014]+|o\s+)+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+")
_FIRST_WORD = re.compile(r"[A-Za-z]+")


def detect_action_verbs(text: str) -> List[str]:
    """Return the distinct action verbs that start a bullet or sentence."""
    if not text:
        return []

    found = set()
    for line in _BULLET_GLYPHS.sub("\n", text).splitlines():
        line = _LEADING_JUNK.sub("", line.strip())
        if not line:
            continue
        for sentence in _SENTENCE_SPLIT.split(line):
            sentence = _LEADING_JUNK.sub("", sentence.strip())
            match = _FIRST_WORD.match(sentence)
            if match and match.group(0).lower() in ACTION_VERBS:
                found.add(match.group(0).lower())

    return sorted(found)
