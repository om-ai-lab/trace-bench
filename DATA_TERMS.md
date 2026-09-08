# Open Stream Bench Data Terms

Status: v1.1.0 local publication candidate; upstream license confirmations are
still being collected. These terms do not establish permission to redistribute
source-derived annotations whose upstream permission remains unresolved.

These terms describe the intended use of the annotation and index files in
`data/releases/v1.1.0`. They do not relicense upstream datasets, source videos,
model weights, or code copied from another project. Where an upstream term is
more restrictive, the upstream term controls.

## Permitted Use

To the extent OSB contributors own the rights, their newly created annotations
and temporal fields are offered under
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-nc-sa/4.0/)
([legal code](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode)).
Give appropriate credit, identify modifications, and share adaptations under
the applicable ShareAlike terms. The linked license controls this grant.
This grant applies only to contributor-owned material, not upstream questions,
options, answers, videos or other material OSB cannot independently license.

Commercial uses are outside that grant unless separately authorized by all
relevant rights holders. NonCommercial has the meaning in the license; merely
making a project open source or not selling the benchmark does not establish
permission for every use or for redistributing upstream annotations.

## Source Data And Videos

OSB does not redistribute the original source videos. Users must obtain source
datasets and videos directly from their original providers and comply with
their download, copyright, privacy, and usage terms. A path or download link in
OSB metadata is not a grant of video redistribution rights.

The release combines provenance from multiple upstream benchmarks:

- [StreamingBench](https://github.com/THUNLP-MT/StreamingBench) code is
  MIT-licensed, but the license for its complete annotation/data release must
  be confirmed with the maintainers. The upstream project and data links are
  listed in its repository and [Hugging Face dataset page](https://huggingface.co/datasets/mjuicem/StreamingBench).
- [OVO-Bench](https://github.com/JoeLeelyf/OVO-Bench) code is MIT-licensed. Its
  GitHub documentation states
  CC BY-NC-SA 4.0 for the dataset, while current Hugging Face metadata states
  CC BY-SA 4.0. See the [upstream dataset page](https://huggingface.co/datasets/JoeLeelyf/OVO-Bench).
  Until the authors clarify this discrepancy, OSB follows the more restrictive
  CC BY-NC-SA 4.0 interpretation, including attribution and ShareAlike.

Questions, options, identifiers, and other source-derived text may remain
subject to upstream rights even when they appear in a canonical OSB record.
OSB's new timing annotations and review-derived fields do not remove those
upstream obligations.

## Attribution

Users should cite Open Stream Bench and the upstream benchmark papers and
repositories used by each record. Preserve this file, the release manifest,
and any applicable upstream notices in redistributed research derivatives.
Nothing in the repository implies endorsement, certification, or partnership
with an upstream project or model author.

## No Warranty

The data is provided for research use without warranty. Users are responsible
for verifying that their intended use complies with all applicable laws,
licenses, access restrictions, and the terms of the original video and dataset
providers.

## Contact And Updates

License clarifications from StreamingBench, OVO-Bench, source-video providers,
or annotation contributors may result in a new data release or an update to
these terms. The release manifest and file hashes identify the exact data
version used by an evaluation.
