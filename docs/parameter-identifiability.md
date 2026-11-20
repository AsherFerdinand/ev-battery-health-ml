# Thevenin parameter identifiability

**Hybrid B uses capacity Q and series resistance R₀ normalized to 298.15 K.** Q remains vulnerable to bias and short or weak excitation. The filter holds R₁ and C₁ fixed. Recovery of the RC time constant τ and its conversion to C₁ were too sensitive to observation quality in this experiment to justify routine adaptation.

## Method

The matched study uses the v1.3 family 4 profile, so 180 s observes an initial rest and a stepped discharge. The 420 s interval additionally sees a charge reversal and another rest. The reference cell has 76% capacity SOH, initial SOC 0.77, resistance scale 1.22 and C₁ = 880 F. Treat initial SOC as an unknown nuisance variable. Fit log Q, log R₀, log R₁ and log τ jointly with SOC using bounded nonlinear least squares. This is a physics recovery diagnostic, separate from the deployed ML features and model selection. The experiment presumes known OCV and series resistance temperature laws, initially relaxed polarisation and one-second held current intervals. Measured temperature enters the electrical predictor directly. It supplies no hidden thermal state or extra heat-balance constraint.

The analytic voltage sensitivities agree with the matched simulator and finite differences. Singular values of the column-normalized Jacobian characterize local separation independently of units. The voltage-only precision calculation assumes independent 3 mV measurement noise and exact current and temperature. The seeded recovery trials relax the latter assumption by feeding all three noisy measured channels to the fitter. Each row below uses 12 realizations from seeds 9821–9832.

## Results

At rest, the 5-column Jacobian has rank 1. Voltage constrains SOC under the assumed OCV curve, and the four parameter columns vanish. The stepped profiles give local rank 5 and recover the known parameters with noiseless observations. This demonstrates local structural separation for the assumed model and excitation. It does not establish global uniqueness or transferable electrochemical parameters.

At 298.15 K over 180 s, a 0.1 change in the log of Q, R₀, R₁ or τ produces a local RMS voltage response of approximately 3.48, 7.26, 3.45 or 0.85 mV, respectively. Under one-quarter applied current the corresponding responses are 0.84, 1.81, 0.86 and 0.21 mV. The warm response to the R₀ perturbation is 5.54 mV at 313.15 K, versus 9.67 mV at 282.15 K. This comparison holds the temperature factor known. It does not estimate that factor from data.

The normalized condition number falls from 12.78 at 180 s to 9.20 at 420 s. The local correlation between log Q and log R₁ falls from +0.65 to +0.33, while log R₁ and log τ correlation changes from +0.33 to −0.31. Duration and load excitation change together in this protocol.

| Conditions | Window | Q | R₀ | R₁ | τ | Derived C₁ |
|---|---:|---:|---:|---:|---:|---:|
| 282.15 K, nominal noise | 180 s | 1.53% | 1.34% | 3.15% | 9.13% | 8.80% |
| 313.15 K, nominal noise | 180 s | 1.97% | 2.20% | 3.31% | 8.98% | 7.18% |
| 298.15 K, nominal noise | 180 s | 1.71% | 1.73% | 3.24% | 9.15% | 7.55% |
| 298.15 K, nominal noise | 420 s | 0.99% | 0.90% | 1.33% | 3.89% | 4.59% |
| 298.15 K, triple sensor noise and +60 mA bias | 180 s | 5.01% | 5.72% | 13.32% | 25.52% | 21.34% |
| 298.15 K, triple sensor noise and +60 mA bias | 420 s | 10.08% | 2.55% | 6.11% | 27.69% | 23.76% |

Entries are median absolute relative recovery errors. The 180 s stress runs had a maximum Q error of 33.0%. At 420 s the median R₀ error improved while the median Q error worsened, illustrating that a longer biased record can produce a worse capacity estimate despite improved conditioning. This study varies noise and current bias together and cannot separate their effects. It uses synthetic matched ECM data and does not claim identifiability on diffusion or NASA records.

Reproduce with `python parameter_identifiability.py`. Verify with `python -m unittest discover -s tests -p test_parameter_identifiability.py -v`.
