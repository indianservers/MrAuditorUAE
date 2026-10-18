import {test} from 'node:test';import assert from 'node:assert/strict';
import {features,fit,transform} from '../src/features.js';import {metrics,ranking} from '../src/metrics.js';
test('train-only preprocessing and unavailable fields',()=>{const a=fit([[1,0],[3,0]]);assert.deepEqual(a.mean,[2,0]);assert.equal(transform([[100,0]],a)[0][0],10);assert.throws(()=>transform([[1]],a));});
test('independent confusion and budget fixtures',()=>{assert.deepEqual(metrics([0,0,1,1],[.1,.8,.9,.7]).confusion_matrix,[[1,1],[0,2]]);assert.equal(ranking([0,1,0,1],[0,1,0,1])[0].precision,1);});
test('features never use label or future records',()=>{const r={id:'1',journal:'a',client:'c',date:'2025-01-01',debit:100,credit:0,currency:'AED',functional_currency:'AED',description:'Revenue',account:'1'};assert.deepEqual(features([r])[0],features([{...r,label:1},{...r,id:'2',date:'2026-01-01',debit:999999}])[0]);});
