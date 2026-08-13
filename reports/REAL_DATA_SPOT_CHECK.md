# Selected Real MATLAB Detection Spot Check

Real data was not used for training or population-level statistics. Five fixed parser-clean files were selected from three projects.

- `musaelab-amplitude-modulation/ama_toolbox/conv_fft.m`: 11 boundaries, 2 recommendations, 0 low-parse
- `musaelab-amplitude-modulation/ama_toolbox/irfft_psd.m`: 14 boundaries, 0 recommendations, 0 low-parse
- `alsad-pw-wvd/Functions/TFD/filter_tfd.m`: 2 boundaries, 0 recommendations, 0 low-parse
- `alsad-pw-wvd/Functions/TFD/tf2af.m`: 4 boundaries, 0 recommendations, 0 low-parse
- `compneuro-rshrf/rsHRF_find_event_vector.m`: 3 boundaries, 1 recommendations, 0 low-parse

Total: 34 candidate boundaries and 3 recommendations; low-parse boundaries: 0. Gate F is NOT_EVALUATED because this spot check must not be generalized to the heterogeneous corpus.
