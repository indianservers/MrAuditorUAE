# Synthetic local document-worker fixtures

UAE/AED and India/INR folders contain a text PDF, a real raster scan and a ZIP
with two distinct fictional invoices. These files test local extraction,
original-byte hashes, separate ZIP documents, explicit member selection and
unverified review states. They do not qualify invoice authenticity, tax rates,
recoverability, Arabic/Hindi OCR accuracy or any actual client population.

`expected.json` records literal text expectations and original file hashes.
The arithmetic amounts are test data, not a legal tax computation. A batch ZIP
must preserve both documents and leave the aggregate invoice fields blank;
select `invoice.pdf` to extract that member separately. Every result still
requires independent human field review.
