#   Copyright 2022 Entropica Labs
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from __future__ import annotations

import numpy as np
import random

from copy import deepcopy
from .qaoa_parameters.extendedparams import QAOAVariationalExtendedParams 
from .qaoa_parameters.baseparams import QAOAVariationalBaseParams
from .basebackend import QAOABaseBackend
from .optimizers.logger_vqa import Logger
from .cost_function import cost_function


def update_and_compute_expectation(backend_obj: QAOABaseBackend, 
                                   params: QAOAVariationalBaseParams, 
                                   logger: Logger):
    """
    Helper function that returns a callable that takes in a list/nparray of raw parameters.
    This function will handle:
    
        #. Updating logger object with `logger.log_variables`
        #. Updating variational parameters with `update_from_raw` 
        #. Computing expectation with `backend_obj.expectation`
    
    Parameters
    ----------
    backend_obj: QAOABaseBackend
        `QAOABaseBackend` object that contains information about the backend that is being used to perform the QAOA circuit
    params : QAOAVariationalBaseParams
        `QAOAVariationalBaseParams` object containing variational angles. 
    logger: Logger
        Logger Class required to log information from the evaluations required for the jacobian/hessian computation.
    Returns
    -------
    out:
        A callable that accepts a list/array of parameters, and returns the computed expectation value. 
    """
    
    def fun(args, n_shots=None):
        current_total_eval = logger.func_evals.best[0]
        current_total_eval += 1
        current_jac_eval = logger.jac_func_evals.best[0]
        current_jac_eval += 1
        logger.log_variables({'func_evals': current_total_eval, 
                              'jac_func_evals': current_jac_eval})
        params.update_from_raw(args)
        
        n_shots_dict = {'n_shots':n_shots} if n_shots else {}
        return backend_obj.expectation(params, **n_shots_dict)

    return fun


def update_and_get_counts(  backend_obj: QAOABaseBackend, 
                            params: QAOAVariationalBaseParams, 
                            logger: Logger):
    
    """
    Helper function that returns a callable that takes in a list/nparray of raw parameters.
    This function will handle:
        (1) Updating logger object with `logger.log_variables`
        (2) Updating variational parameters with `update_from_raw` 
        (3) Getting the counts dictonary with `backend_obj.get_counts`
    
    PARAMETERS
    ----------
    backend_obj: QAOABaseBackend
        `QAOABaseBackend` object that contains information about the backend that is being used to perform the QAOA circuit
        
    params : QAOAVariationalBaseParams
        `QAOAVariationalBaseParams` object containing variational angles.
        
    logger: Logger
        Logger Class required to log information from the evaluations required for the jacobian/hessian computation.
    
    Returns
    -------
    out:
        A callable that accepts a list/array of parameters, and returns the counts dictonary. 
    """
    
    def fun(args, n_shots=None):
        current_total_eval = logger.func_evals.best[0]
        current_total_eval += 1
        current_jac_eval = logger.jac_func_evals.best[0]
        current_jac_eval += 1
        logger.log_variables({'func_evals': current_total_eval, 
                              'jac_func_evals': current_jac_eval})
        params.update_from_raw(args)
        
        n_shots_dict = {'n_shots':n_shots} if n_shots else {}
        return backend_obj.get_counts(params, **n_shots_dict)

    return fun


def derivative(backend_obj: QAOABaseBackend, 
               params: QAOAVariationalBaseParams, 
               logger: Logger, 
               derivative_type: str = None, 
               derivative_method: str = None, 
               derivative_options: dict = None):
    """
    Returns a callable function that calculates the gradient according to the specified `gradient_method`.

    Parameters
    ----------
    backend_obj: QAOABaseBackend
        `QAOABaseBackend` object that contains information about the backend that is being used to perform the QAOA circuit
    params : QAOAVariationalBaseParams
        `QAOAVariationalBaseParams` object containing variational angles.
    logger: Logger
        Logger Class required to log information from the evaluations required for the jacobian/hessian computation.
    derivative_type : str
        Type of derivative to compute. Either `gradient` or `hessian`.
    derivative_method : str
        Computational method of the derivative. Either `finite_difference`, `param_shift`, `stoch_param_shift`, or `grad_spsa`.
    derivative_options : dict
        Dictionary containing options specific to each `derivative_method`.
    cost_std : QAOACost
        `QAOACost` object that computes expectation values when executed. Standard parametrisation.
    cost_ext : QAOACost
        `QAOACost` object that computes expectation values when executed. Extended parametrisation. Mainly used to compute parameter shifts at each individual gate, which is summed to recover the parameter shift for a parametrised layer.
    Returns
    -------
    out:
        The callable derivative function of the cost function, generated based on the `derivative_type`, `derivative_method`, and `derivative_options` specified.
    """
    # Default derivative_options used if none are specified.
    default_derivative_options = {"stepsize": 0.00001,
                                  "n_beta_single": -1,
                                  "n_beta_pair": -1,
                                  "n_gamma_single": -1,
                                  "n_gamma_pair": -1}

    derivative_options = {**default_derivative_options, **derivative_options
                          } if derivative_options is not None else default_derivative_options

    # cost_std = derivative_dict['cost_std']
    # cost_ext = derivative_dict['cost_ext']
    params_ext = QAOAVariationalExtendedParams.empty(backend_obj.circuit_params)

    derivative_types = ['gradient', 'gradient_w_variance', 'hessian']
    assert derivative_type in derivative_types,\
        "Unknown derivative type specified - please choose between " + \
        str(derivative_types)

    derivative_methods = ['finite_difference',
                          'param_shift', 'stoch_param_shift', 'grad_spsa']
    assert derivative_method in derivative_methods,\
        "Unknown derivative computation method specified - please choose between " + \
        str(derivative_methods)
    
    params = deepcopy(params)

    if derivative_type == 'gradient':

        if derivative_method == 'finite_difference':
            out = grad_fd(backend_obj, params, derivative_options, logger)
        elif derivative_method == 'param_shift':
            assert params.__class__.__name__ == 'QAOAVariationalStandardParams', f"{params.__class__.__name__} not supported - only Standard Parametrisation is supported for parameter shift/stochastic parameter shift for now."
            out = grad_ps(backend_obj, params, params_ext, logger)
        elif derivative_method == 'stoch_param_shift':
            assert params.__class__.__name__ == 'QAOAVariationalStandardParams', f"{params.__class__.__name__} not supported - only Standard Parametrisation is supported for parameter shift/stochastic parameter shift for now."
            out = grad_sps(backend_obj, params, params_ext, derivative_options, logger)
        elif derivative_method == 'grad_spsa':
            out = grad_spsa(backend_obj, params, derivative_options, logger)

    elif derivative_type == 'gradient_w_variance':

        #TODO: complete this
        if derivative_method == 'finite_difference':
            out = grad_fd(backend_obj, params, derivative_options, logger, variance=True)
        elif derivative_method == 'param_shift':
            assert params.__class__.__name__ == 'QAOAVariationalStandardParams', f"{params.__class__.__name__} not supported - only Standard Parametrisation is supported for parameter shift/stochastic parameter shift for now."
            out = grad_ps(backend_obj, params, params_ext, logger, variance=True)
        elif derivative_method == 'stoch_param_shift':
            assert params.__class__.__name__ == 'QAOAVariationalStandardParams', f"{params.__class__.__name__} not supported - only Standard Parametrisation is supported for parameter shift/stochastic parameter shift for now."
            out = grad_sps(backend_obj, params, params_ext, derivative_options, logger, variance=True)
        elif derivative_method == 'grad_spsa':
            out = grad_spsa(backend_obj, params, derivative_options, logger, variance=True)


    elif derivative_type == 'hessian':

        if derivative_method == 'finite_difference':
            out = hessian_fd(backend_obj, params, derivative_options, logger)
        else:
            raise ValueError('Only support hessian derivative method is finite_difference. Your choice: {}'.format(derivative_method))

    return out


def __create_n_shots_list(n_params, n_shots):

    # If n_shots is a list, then it must be of length n_params, else create a list of length n_params with all elements equal to n_shots
    if isinstance(n_shots, list):
        assert len(n_shots) == n_params, "n_shots must be a list of length equal to the number of parameters."
        n_shots_list = n_shots
    elif isinstance(n_shots, int) or n_shots is None:
        n_shots_list = [n_shots] * n_params
    else:
        raise ValueError("n_shots must be either an integer or a list of integers.")

    return n_shots_list


def __create_n_shots_ext_list(n_params, n_associated_params, n_shots):
    """
    Creates a list of number of shots for each parameter in the extended parametrisation. 
    If n_shots is a integer, then it is used for all extended parameters. So, we create a list of length sum(n_associated_params) 
    with all elements equal to n_shots. (sum(n_associated_params) = number of extended params)
    If n_shots is a list, then this list tell us the number of shots for each standard parameter. We convert this list to a list of
    number of shots for each extended parameter. Each standard parameter has a different number of associated extended parameters,
    `n_associated_params` helps us with this. Each element of `n_associated_params` is the number of associated extended parameters to each coefficient.
    And we know that each standard parameter has 2 associated coefficients (mixer_1q, mixer_2q, cost_1q, cost_2q).
    
    Parameters
    ----------
    n_associated_params : list
        List of integers, where each integer is the number of associated parameters in the extended parametrisation for each coefficient.
        The sum of all elements in this list is equal to the number of parameters in the extended parametrisation.
    n_params : int
        Number of parameters in the standard parametrisation.
    n_shots : int or list
        Number of shots to use for each parameter in the standard parametrisation. 
        If an integer, then it is used for all the extended parameters. 
        If a list, then it must be of length sum(n_associated_params).

    Returns
    -------
    n_shots_ext_list : list
        List of integers, where each integer is the number of shots to use for each parameter in the extended parametrisation.
    """

    # If n_shots is a list, then it must be of length n_params, else create a list of length n_params with all elements equal to n_shots
    if isinstance(n_shots, list):
        assert len(n_shots) == n_params, "n_shots must be a list of length equal to the number of parameters."

        # transform n_shots list (which has length n_params) into a list of the same length of n_associated_params
        n_shots = np.array(n_shots)
        n_shots = n_shots.reshape(2, len(n_shots)//2).repeat(2, axis=0).reshape(n_shots.size*2) # repeat each element twice in the following way: if we have [1,2,3,4] we get [1,2,1,2,3,4,3,4]

        # create the list of n_shots for each parameter in the extended parametrisation. For each parameter of each coefficient we have a number of shots (`n_shots` list), we need to repeat this number of shots the number of associated extended parameters that each coefficient has (`n_associated_params` list).
        n_shots_list = [shots for r, shots in zip(n_associated_params, n_shots) for _ in range(r)]
    elif isinstance(n_shots, int) or n_shots is None:
        n_shots_list = [n_shots] * np.sum(n_associated_params)
    else:
        raise ValueError("n_shots must be either an integer or a list of integers.")

    return n_shots_list

def __gradient(args, backend_obj, params, logger, variance):
    """
    returns a callable function that Computes the gradient and its variance for the i-th parameter using finite difference.
    Or the gradient and its variance using spsa.
    """    

    def fun_w_variance(vect_eta, constant, n_shots=None):
        """
        Computes the gradient and its variance . TODO
        """

        # get value of eta, the function to get counts, hamiltonian, and alpha
        fun = update_and_get_counts(backend_obj, params, logger)
        hamiltonian = backend_obj.circuit_params.cost_hamiltonian
        alpha = backend_obj.cvar_alpha

        # get counts f(x+eta/2) and f(x-eta/2)
        counts_i_dict = fun(args - vect_eta, n_shots=n_shots)
        counts_f_dict = fun(args + vect_eta, n_shots=n_shots)

        #compute cost for each state in the counts dictionaries
        costs_dict = {key: cost_function({key: 1}, hamiltonian, alpha) for key in counts_i_dict.keys() | counts_f_dict.keys()}

        # for each count get the cost and create a list of shot costs
        eval_i_list = [costs_dict[key] for key, value in counts_i_dict.items() for _ in range(value)]
        eval_f_list = [costs_dict[key] for key, value in counts_f_dict.items() for _ in range(value)]

        # compute a list of gradients of one shot cost
        grad_list =  np.real(constant*(np.array(eval_f_list) - np.array(eval_i_list)))
        
        # return average and variance for the gradient for this argument
        return np.mean(grad_list), np.var(grad_list)

    def fun(vect_eta, constant, n_shots=None):
        """
        Computes the gradient : TODO
        """
        fun = update_and_compute_expectation(backend_obj, params, logger)
        return constant*(fun(args + vect_eta, n_shots=n_shots) - fun(args - vect_eta, n_shots=n_shots)), 0

    if variance:    return fun_w_variance
    else:           return fun

    
def grad_fd(backend_obj, params, gradient_options, logger, variance:bool=False):
    """
    Returns a callable function that calculates the gradient (and its variance if `variance=True`) with the finite difference method.

    PARAMETERS
    ----------
    backend_obj : `QAOABaseBackend`
        backend object that computes expectation values when executed. 
    params : `QAOAVariationalBaseParams`
        parameters of the variational circuit.
    gradient_options : `dict`
        stepsize : 
            Stepsize of finite difference.
    logger : `Logger`
        logger object to log the number of function evaluations.
    variance : `bool`
        If True, the variance of the gradient is also computed.
        If False, only the gradient is computed.

    RETURNS
    -------
    grad_fd_func: `Callable`
        Callable derivative function.
    """

    # Set default value of eta
    eta = gradient_options['stepsize']

    def grad_fd_func(args, n_shots=None):

        # get the function to compute the gradient and its variance
        __gradient_function = __gradient(args, backend_obj, params, logger, variance)     

        # if n_shots is int or None create a list with len of args (if it is none, it will use the default n_shots)
        n_shots_list = __create_n_shots_list(len(args), n_shots)

        # if variance is True, add the number of shots per argument to the logger
        if variance: logger.log_variables({'n_shots': n_shots_list})

        # lists of gradients and variances for each argument, initialized with zeros
        grad, var = np.zeros(len(args)), np.zeros(len(args))

        for i in range(len(args)):
            # vector and constant to compute the gradient for the i-th argument
            vect_eta = np.zeros(len(args))
            vect_eta[i] = eta/2
            const = 1/eta
            
            # Finite diff. calculation of gradient
            grad[i], var[i] = __gradient_function(vect_eta, const, n_shots_list[i]) # const*[f(args + vect_eta) - f(args - vect_eta)]

        if variance:  return grad, var, 2*sum(n_shots_list)   #return gradient, variance, and total number of shots
        else:         return grad                             #return gradient

    return grad_fd_func


def grad_ps(backend_obj, params, params_ext, logger, variance:bool=False):
    """
    Returns a callable function that calculates the gradient (and its variance if `variance=True`) with the parameter shift method.

    PARAMETERS
    ----------
    backend_obj : `QAOABaseBackend`
        backend object that computes expectation values when executed. 
    params : `QAOAVariationalStandardParams`
        variational parameters object, standard parametrisation.
    params_ext : `QAOAVariationalExtendedParams`
        variational parameters object, extended parametrisation.
    logger : `Logger`
        logger object to log the number of function evaluations.
    variance : `bool`
        If True, the variance of the gradient is also computed.
        If False, only the gradient is computed.
    
    RETURNS
    -------
    grad_ps_func:
        Callable derivative function.
    """    
    # TODO : handle Fourier parametrisation

    # list of coefficients
    coeffs_list = params.p*params.mixer_1q_coeffs + params.p*params.mixer_2q_coeffs + params.p*params.cost_1q_coeffs + params.p*params.cost_2q_coeffs
    
    # create a list of how many extended parameters are associated with each coefficient 
    n_associated_params = np.repeat([len(params.mixer_1q_coeffs), len(params.mixer_2q_coeffs), len(params.cost_1q_coeffs), len(params.cost_2q_coeffs)], params.p)
    # with the `n_associated_params` list, add a 0 in the first position and sum the list cumulatively (so that this list indicate which gate is associated with which coefficient) 
    l = np.insert(np.cumsum(n_associated_params), 0, 0) # the i-th coefficient is associated with extended parameters with indices in range [l[i], l[i+1]]

    def grad_ps_func(args, n_shots=None):

        # Convert standard to extended parameters before applying parameter shift
        args_ext = params.convert_to_ext(args)

        # get the function to compute the gradient and its variance
        __gradient_function = __gradient(args_ext, backend_obj, params_ext, logger, variance)

        # if variance is True, add the number of shots per argument (standard) to the logger
        if variance: logger.log_variables({'n_shots': __create_n_shots_list(len(args), n_shots)})

        # we call the function that returns the number of shots for each extended parameter, giving the number of shots for each standard parameter (n_shots)
        n_shots_list = __create_n_shots_ext_list(len(args), n_associated_params, n_shots)

        ## compute the gradient (and variance) of all extended parameters with the stochastic parameter shift method
            # lists of gradients and variances for each argument (extended), initialized with zeros
        grad_ext, var_ext = np.zeros(len(args_ext)), np.zeros(len(args_ext))
            # Apply parameter shifts
        for i in range(len(args_ext)):
            r = coeffs_list[i]
            vect_eta = np.zeros(len(args_ext))
            vect_eta[i] = (np.pi/(4*r))
            grad_ext[i], var_ext[i] = __gradient_function(vect_eta, r, n_shots_list[i]) # r*[f(args + vect_eta) - f(args - vect_eta)]

        ## convert extended form back into standard form
            # sum all the gradients for each parameter of each coefficient according to the indices in l, and rehape the array to 4 rows and p columns, first row is mixer_1q, second is mixer_2q, third is cost_1q, fourth is cost_2q
        grad = np.array([np.sum(grad_ext[ l[i-1] : l[i] ]) for i in range(0, len(l)-1)]).reshape(4, params.p)
            # summing 1q with 2q gradients (first row with second row, third row with fourth row), to get the gradient for each parameter in the standard form
        grad = np.concatenate((grad[0] + grad[1], grad[2] + grad[3]))
            # repeat the same for the variances
        var = np.array( [np.sum( var_ext[ l[i-1] : l[i] ]) for i in range(0, len(l)-1)]).reshape(4, params.p)
        var = np.concatenate((var[0] + var[1], var[2] + var[3]))
        
        if variance:  return grad, var, 2*sum(n_shots_list)  #return gradient, variance, and total number of shots
        else:         return grad                            #return gradient

    return grad_ps_func


def grad_sps(backend_obj, params_std, params_ext, gradient_options, logger, variance:bool=False):
    """
    Returns a callable function that approximates the gradient (and its variance if `variance=True`) with the stochastic parameter shift method, which samples (n_beta_single, n_beta_pair, n_gamma_single, n_gamma_pair) gates at each layer instead of all gates. See "Algorithm 4" of https://arxiv.org/pdf/1910.01155.pdf. By convention, (n_beta_single, n_beta_pair, n_gamma_single, n_gamma_pair) = (-1, -1, -1, -1) will sample all gates (which is then equivalent to the full parameter shift rule).

    PARAMETERS
    ----------
    backend_obj : `QAOABaseBackend`
        backend object that computes expectation values when executed. 
    params_std : `QAOAVariationalStandardParams`
        variational parameters object, standard parametrisation.
    params_ext : `QAOAVariationalExtendedParams`
        variational parameters object, extended parametrisation.
    gradient_options :
        n_beta_single : 
            Number of single-qubit mixer gates to sample for the stochastic parameter shift.
        n_beta_pair : 
            Number of X two-qubit mixer gates to sample for the stochastic parameter shift.
        n_gamma_pair : 
            Number of two-qubit cost gates to sample for the stochastic parameter shift.
        n_gamma_single : 
            Number of single-qubit cost gates to sample for the stochastic parameter shift.
    logger : `Logger`
        logger object to log the number of function evaluations.
    variance : `bool`
        If True, the variance of the gradient is also computed.
        If False, only the gradient is computed.

    RETURNS
    -------
    grad_sps_func:
        Callable derivative function.
    """

    # list of the names of the parameters and list of the number of gates for each parameter
    names_params = ['n_beta_single', 'n_beta_pair', 'n_gamma_single', 'n_gamma_pair']
    n_sample = [gradient_options[x] for x in names_params]

    # list of the number of gates for each parameter if all gates are sampled (equivalent to the full parameter shift rule)
    n_sample_equivalent_ps = [len(x) for x in [params_std.mixer_1q_coeffs, params_std.mixer_2q_coeffs, params_std.cost_1q_coeffs, params_std.cost_2q_coeffs]]

    # check if the number of gates to sample is valid and if it is -1 then set it to the number of gates in the full parameter shift rule
    for i, (x, y) in enumerate(zip(n_sample, n_sample_equivalent_ps)): 
        assert -1 <= x <= y, f"Invalid {names_params[i]}, it must be between -1 and {y}, but {x} is passed."
        if x == -1: n_sample[i] = y
    
    # list of the coefficients
    coeffs_list = params_std.p*params_std.mixer_1q_coeffs + params_std.p*params_std.mixer_2q_coeffs + params_std.p*params_std.cost_1q_coeffs + params_std.p*params_std.cost_2q_coeffs

    # create a list of how many gates are associated with each coefficient 
    n_associated_params = np.repeat(n_sample, params_std.p)
    
    # create a list of how many extended parameters are associated with each coefficient (equivalent to the full parameter shift rule)
    n_associated_params_equivalent_ps = np.repeat(n_sample_equivalent_ps, params_std.p)
    # with the `n_associated_params_equivalent_ps` list, add a 0 in the first position and sum the list cumulatively (so that this list indicate which gate is associated with which coefficient) 
    l = np.insert(np.cumsum(n_associated_params_equivalent_ps), 0, 0) # the i-th coefficient is associated with extended parameters with indices in range [l[i], l[i+1]]
    
    def grad_sps_func(args, n_shots=None):

        # Convert standard to extended parameters before applying parameter shift
        args_ext = params_std.convert_to_ext(args)

        # get the function to compute the gradient and its variance
        __gradient_function = __gradient(args_ext, backend_obj, params_ext, logger, variance)

        # if variance is True, add the number of shots per argument (standard) to the logger
        if variance: logger.log_variables({'n_shots': __create_n_shots_list(len(args), n_shots)})

        # we call the function that returns the number of shots for each extended parameter, giving the number of shots for each standard parameter (n_shots)
        n_shots_list = __create_n_shots_ext_list(len(args), n_associated_params_equivalent_ps, n_shots)

        # define the list of indices of the extended parameters that are associated with each coefficient
        sampled_indices = np.array([])
        for i, n in enumerate(n_associated_params):
            # take n random indices from the range of indices associated with the i-th extended parameter [l[i], l[i+1]]
            sampled_indices = np.append(sampled_indices, np.random.choice(range(l[i], l[i+1]), n, False)) 

        ## compute the gradient (and variance) of all extended parameters (that the sampled indices indicate) with the stochastic parameter shift method
            # lists of gradients and variances for each argument (extended), initialized with zeros
        grad_ext, var_ext = np.zeros(len(args_ext)), np.zeros(len(args_ext))
            # Apply parameter shifts
        n_shots_used = 0
        for i in range(len(args_ext)):
            if i in sampled_indices:        
                r = coeffs_list[i]
                vect_eta = np.zeros(len(args_ext))
                vect_eta[i] = (np.pi/(4*r))
                grad_ext[i], var_ext[i] = __gradient_function(vect_eta, r, n_shots_list[i]) # r*[f(args + vect_eta) - f(args - vect_eta)]
                n_shots_used += 2*n_shots_list[i] if n_shots_list[i] is not None else 0 # keep track of the number of shots used

        ## convert extended form back into standard form
            # sum all the gradients for each parameter of each coefficient according to the indices in l, and rehape the array to 4 rows and p columns, first row is mixer_1q, second is mixer_2q, third is cost_1q, fourth is cost_2q
        grad = np.array([np.sum(grad_ext[ l[i-1] : l[i] ]) for i in range(0, len(l)-1)]).reshape(4, params_std.p)
            # summing 1q with 2q gradients (first row with second row, third row with fourth row), to get the gradient for each parameter in the standard form
        grad = np.concatenate((grad[0] + grad[1], grad[2] + grad[3]))
            # repeat the same for the variances
        var = np.array( [np.sum( var_ext[ l[i-1] : l[i] ]) for i in range(0, len(l)-1)]).reshape(4, params_std.p)
        var = np.concatenate((var[0] + var[1], var[2] + var[3]))
        
        if variance:  return grad, var, n_shots_used  #return gradient, variance, and total number of shots
        else:         return grad                            #return gradient

    return grad_sps_func


def grad_spsa(backend_obj, params, gradient_options, logger, variance:bool=False):
    """
    Returns a callable function that calculates the gradient approxmiation with the Simultaneous Perturbation Stochastic Approximation (SPSA) method.

    PARAMETERS
    ----------
    backend_obj : `QAOABaseBackend`
        backend object that computes expectation values when executed. 
    params : `QAOAVariationalBaseParams`
        variational parameters object.
    gradient_options : `dict`
        gradient_stepsize : 
            stepsize of stochastic shift.
    logger : `Logger`
        logger object to log the number of function evaluations.

    RETURNS
    -------
    grad_spsa_func: `Callable`
        Callable derivative function.

    """
    eta = gradient_options['stepsize']

    def grad_spsa_func(args, n_shots=None):

        # if variance is True, add the number of shots per argument to the logger
        if variance: logger.log_variables({'n_shots': [n_shots]})

        # get the function to compute the gradient and its variance            
        __gradient_function = __gradient(args, backend_obj, params, logger, variance)

        # vector and constant to compute the gradient and its variance
        delta = (2*np.random.randint(0, 2, size=len(args))-1)
        vector_eta = delta*eta/2
        const = 1/eta

        # compute the gradient and its variance: const*[f(args + vect_eta) - f(args - vect_eta)]
        grad, var = __gradient_function(vector_eta, const, n_shots)

        if variance:  return grad*delta, var*np.abs(delta), 2*n_shots   # return the gradient, its variance and the total number of shots
        else:         return grad*delta                                 # return the gradient

    return grad_spsa_func


def hessian_fd(backend_obj, params, hessian_options, logger):
    """
    Returns a callable function that calculates the hessian with the finite difference method.

    PARAMETERS
    ----------
    backend_obj : `QAOABaseBackend`
        backend object that computes expectation values when executed.
    params : `QAOAVariationalBaseParams`
        variational parameters object.
    hessian_options :
        hessian_stepsize : 
            stepsize of finite difference.
    logger : `Logger`
        logger object to log the number of function evaluations.

    RETURNS
    -------
    hessian_fd_func:
        Callable derivative function.

    """

    eta = hessian_options['stepsize']
    fun = update_and_compute_expectation(backend_obj, params, logger)

    def hessian_fd_func(args):
        hess = np.zeros((len(args), len(args)))

        for i in range(len(args)):
            for j in range(len(args)):
                vect_eta1 = np.zeros(len(args))
                vect_eta2 = np.zeros(len(args))
                vect_eta1[i] = 1
                vect_eta2[j] = 1

                if i == j:
                    # Central diff. hessian diagonals (https://v8doc.sas.com/sashtml/ormp/chap5/sect28.htm)
                    hess[i][i] = (-fun(args+2*eta*vect_eta1) + 16*fun(args + eta*vect_eta1) - 30*fun(
                        args) + 16*fun(args-eta*vect_eta1)-fun(args-2*eta*vect_eta1))/(12*eta**2)
                #grad_diff[i] = (grad_fd_ext(params + (eta/2)*vect_eta)[i] - grad_fd_ext(params - (eta/2)*vect_eta)[i])/eta
                else:
                    hess[i][j] = (fun(args + eta*vect_eta1 + eta*vect_eta2)-fun(args + eta*vect_eta1 - eta*vect_eta2)-fun(
                        args - eta*vect_eta1 + eta*vect_eta2)+fun(args - eta*vect_eta1 - eta*vect_eta2))/(4*eta**2)

        return hess

    return hessian_fd_func