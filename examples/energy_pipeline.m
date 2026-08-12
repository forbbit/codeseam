raw = randn(1, 256);
cutoff = 0.25;
if mean(raw) > cutoff
    prepared = detrend(raw);
else
    prepared = raw - median(raw);
end
scale = max(abs(prepared));
normalized = prepared / max(scale, eps);
spectrum = abs(fft(normalized));
peak = max(spectrum);
disp(peak);
